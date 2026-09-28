# W11 — Quiet week or real role change?

**Status: COMPLETE.**

**Pre-registered verdict: NO EFFECT**, in both Full PPR and Half-PPR.

- **Stage 1: the mechanism is ESTABLISHED at RB, WR and TE**, under all three threshold sets.
- **Stage 2:** giving W10's model the role-change signal leaves RB unchanged (+0.004
  capture@10, not significant) and keeps the WR gain (−0.002). **There is no breach.**

Run as pre-registered in `docs/weekly/W11_PREREGISTRATION.md`:

- the pre-registration was committed at `8718f07`, before any W11 comparison existed;
- the instruments were committed at `6d40a1b`, before any result was read;
- **amendment A1 (`e2f88f7`) fixed a bug** that left one reported statistic (R) empty. It was
  found after stage 1 was read; stage 1 was regenerated and re-gated before R was read (§6).

**Research only. Production diff EMPTY. ECR is a benchmark only, never a feature** (gate G5).
**No news, injury or external data was added.**

**This is retrospective research, not confirmation.** The 2021–2025 weeks shaped the hypothesis.
The repository holds no 2026 data, and the 2026 protocol is frozen (pre-registration §10).

---

## Can Alpha remember who a player is without becoming blind to a real role change?

**Not with the information it already has.**

**The blindness is real, and it can be seen before Friday.** A simple pre-registered rule flags
a sustained role change: two straight games at least 3 touches, or 15 snap-share points, away from
last season. That rule:

- **finds changes that last.** A flagged RB riser averages **+5.2 touches** over last season in
  the predicted week; a one-game spike averages +1.7.
- **splits W10's memory exactly into help and harm.** The historical model loses capture on
  sustained risers at every position, in every season and in every part of the season (RB
  −0.053, WR −0.033 capture@10). It gains on quiet stable players, on decliners and on one-game
  fluctuations.

**But giving the model that signal does not fix it.**

- The loss on sustained risers moves by **+0.0001** at RB and at WR.
- RB's top 10 improves by +0.004, which is noise. WR keeps its W10 gain. Nothing breaks.

**The reason is in the diagnostics.** History's demotion of a rising player is usually *right*:

- the historical model ranks risers lower than current Alpha does;
- its rank errors on them are smaller on average;
- it makes a third fewer false top-10 picks among them (RB 65 → 44).

What it loses is the minority of risers who have a genuinely huge week. Top-5 RB finishers it
ranked outside the top 24 rise from 10 to 18.

"This player's role grew" is true of both the many modest risers and the few breakouts, so it
cannot tell them apart. On average, demoting them is the right call. **The penalty is not stale
memory that current role can overwrite. It is the upside tail, and the repository's pre-Friday
data does not identify it.**

**Following the brief's decision tree:**

- W10 stays useful for WR;
- RB needs a different kind of information;
- the next step is timestamped weekly information.

---

## 1. Stage 1: the mechanism

B − A capture@10, split exactly by the PRIMARY class of each player entering or leaving the top
10. Full PPR, 79 weeks; \* = 95% CI excludes 0. **The pre-registered tests are QUIET > 0 (M1) and
ROLE_UP < 0 (M2).**

| class | RB | WR | TE |
|---|---:|---:|---:|
| **QUIET** (role intact, production down) | **+0.015\*** | **+0.050\*** | **+0.019\*** |
| STABLE (role intact, production up) | +0.002 | −0.016\* | −0.006 |
| **ROLE_UP** (sustained increase) | **−0.053\*** | **−0.033\*** | **−0.020\*** |
| ROLE_DOWN (sustained decrease) | +0.025\* | +0.013\* | +0.008\* |
| TRANSIENT (one-game fluctuation) | +0.018\* | +0.014\* | +0.009 |
| TOO_EARLY (< 2 games this season) | +0.004 | +0.007 | +0.004 |
| NO_PRIOR (no season S − 1) | −0.012\* | −0.014\* | −0.009\* |
| **total = W10's B − A** | +0.000 | +0.022 | +0.004 |

The WR row also includes ROLE_MIXED, +0.002.

**The mechanism is established at every position.** It is also robust across:

- **threshold sets** (the ROLE_UP cost):

  | | LOOSE | PRIMARY | STRICT |
  |---|---:|---:|---:|
  | RB | −0.057\* | −0.053\* | −0.043\* |
  | WR | −0.048\* | −0.033\* | −0.017\* |
  | TE | −0.028\* | −0.020\* | −0.010\* |

  The QUIET gain is significant under every set.
- **seasons:** ROLE_UP is negative in 5 of 5 seasons at RB (−0.033 to −0.099) and WR (−0.012 to
  −0.065). QUIET is positive in 5/5 at WR and 4/5 at RB.
- **periods** (ROLE_UP):

  | | EARLY | MID | LATE |
  |---|---:|---:|---:|
  | RB | −0.051\* | −0.052\* | −0.055\* |
  | WR | −0.026\* | −0.043\* | −0.030\* |

- **Half-PPR:** identical conclusions (RB ROLE_UP −0.052\*, WR QUIET +0.048\*).

**ROLE_DOWN helps, as predicted.** When a player's current role has shrunk, holding them up on
last season's level is right. Drops are more often temporary than rises.

### R: is a flagged change real or a one-game fluctuation?

This week's realized touches minus last season's per-game level:

| | sustained up | one-game spike up | difference | sustained down | one-game dip | difference |
|---|---:|---:|---:|---:|---:|---:|
| RB | +5.22 (n 830) | +1.71 (540) | **+3.51\*** | −4.98 (959) | −1.69 (552) | **−3.29\*** |
| WR | +1.47 (1,258) | +0.76 (804) | **+0.70\*** | −2.07 (1,137) | −1.09 (759) | **−0.98\*** |
| TE | +1.20 (534) | +0.61 (429) | **+0.59\*** | −1.34 (465) | −0.51 (343) | **−0.83\*** |

- **The persistence rule works:** sustained changes carry into the predicted week, one-game
  spikes mostly revert.
- The RB difference grows through the season: +2.2\* EARLY, +3.6\* MID, +4.3\* LATE. WR goes
  +0.3, +0.7\*, +1.0\*.
- The result holds under LOOSE and STRICT (RB +3.1\* and +3.8\*).

### M3: are the historical model's individual moves wrong more often for role changers?

**No. The opposite.** Among players who move ≥ 3 ranks between A and B inside either top 24, B's
move is *farther* from the realized rank than A's in:

| | role changers | stable players | difference |
|---|---:|---:|---|
| RB | 46.5% | 48.9% | −0.024, CI [−0.114, +0.063] |
| WR | 40.2% | 47.7% | −0.075, CI [−0.159, +0.007] |
| TE | 41.2% | 48.9% | −0.077 |

By class, B's moves on **ROLE_UP** players are right most of the time: wrong 40.8% (RB) and 32.3%
(WR). Its moves on **QUIET** players are wrong 62.1% and 61.3%, yet QUIET is where it *gains*
capture.

**The capture effects come from a few high-scoring weeks, not from the typical move:**

- history's promotions of quiet stars are usually wrong by rank, but the ones that hit score big;
- its demotions of risers are usually right, but the ones that miss were big.

### What the historical model does to risers (PRIMARY ROLE_UP, B against A)

| | rank move (B − A) | mean \|rank error\| change | false top-10 picks A → B | top-5 finishers ranked outside 24, A → B |
|---|---:|---:|---:|---:|
| RB | +2.5 (lower) | −0.36\* (B closer) | 65 → **44** | 10 → **18** |
| WR | +5.6 (lower) | −0.30 | 72 → **41** | 18 → **23** |
| TE | +1.7 (lower) | −0.19 | 46 → 34 | 5 → 4 |

**This table is the core of the answer.** Demoting a rising player removes many false positives,
and on average it brings the ranking closer to the truth. It costs the real breakouts, and
capture@10 weighs those heavily.

---

## 2. Stage 2: the model

Pre-registered rule: stage 2 runs only if the mechanism is established at RB or WR. It was, so
arm C = B + `role_d_opp`, `role_d_snap`, `role_shift` was trained, with everything else frozen.

**C − B, Full PPR** (MDE for capture@10: RB 0.009, WR 0.010, TE 0.008, FLEX 0.011):

| | capture@5 | capture@10 | capture@20 | capture@50 | Spearman | pairwise |
|---|---:|---:|---:|---:|---:|---:|
| RB | +0.000 | +0.004 | +0.003 | −0.001 | +0.0015 | +0.0007 |
| WR | +0.002 | −0.002 | −0.004 | +0.001 | −0.0003 | −0.0004 |
| TE | −0.010 | +0.007 | −0.003 | −0.001 | −0.0015 | −0.0005 |
| FLEX | +0.001 | −0.008 | −0.000 | −0.001 | +0.0005 | +0.0002 |

- FLEX capture@25 is −0.002.
- **FLEX precision@10 is −0.018\*.** The null arm shows the same, −0.019\*, so this is the cost of
  adding three columns, not of role information (C − N +0.001).

**Weeks C wins–loses–ties against B** (capture@10): RB 30–23–26, WR 25–32–22, TE 27–17–35, FLEX
30–35–14.

### The verdict (§7)

| condition | result |
|---|---|
| S1: RB capture@10 C − B ≥ +0.02 (or carried by ROLE_UP ≥ +0.02), CI excluding 0 | ✗ +0.0037, CI [−0.005, +0.013] |
| S2: WR preserved and still beating A | ✔ C − B −0.002; C − A **+0.020\*** |
| S3: no guardrail breach | ✔ none |
| S4: RB beats the role null | ✗ C − N +0.003 |
| S5: RB consistent | ✗ positive in 3/5 seasons; 0/5 LOSO folds significant |

- **No PARTIAL route triggers:**
  - RB C − B is below +0.02;
  - the RB ROLE_UP attribution is +0.0001, CI [−0.007, +0.007];
  - no capture@10 C − B reaches +0.02.
- **Verdict: NO EFFECT.** Half-PPR gives the same.

### Did role awareness touch the penalty it was built for?

C − B capture@10 split by class:

| class | RB | WR | TE |
|---|---:|---:|---:|
| ROLE_UP (the target) | **+0.0001** | **+0.0001** | **+0.010\*** |
| QUIET | +0.004 | +0.001 | −0.005 |
| ROLE_DOWN | −0.007\* | +0.003\* | −0.002 |
| TRANSIENT | +0.008\* | −0.006 | +0.001 |

- **At RB and WR, arm C left the breakout penalty exactly where it was.** The model sees the role
  delta and does not act on it, which is consistent with §1: on average, demoting risers is
  right.
- **TE is the one exception.** Role awareness halves the TE breakout penalty (−0.020 → about
  −0.010), and TE capture@10 against the null is +0.011\*. Against B it is +0.007, CI [−0.000,
  +0.016], and capture@5 −0.010 offsets it. It does not reach any pre-registered bar, and TE is the
  comparison position.

---

## 3. The ten questions

### 1. Can we reliably distinguish a quiet week from a real role change using pre-Friday information?

**As groups, yes. For individual predictions, no.**

- The pre-registered two-game rule identifies changes that persist into the predicted week (R,
  §1).
- It separates the class where W10's memory costs capture (ROLE_UP) from the classes where memory
  helps (QUIET, ROLE_DOWN, TRANSIENT). This holds at every position, season, period and threshold.
- But it does not flag which of the historical model's moves are wrong. Risers' demotions are
  right *more* often than stable players' moves (M3).

**Routes are unavailable in every source**, so the role measures are touches and snap share.

### 2. Does that distinction explain the W10 RB tradeoff?

**Yes, almost exactly.** W10's RB top-10 effect of +0.000 is:

| part | capture@10 |
|---|---:|
| rescues of quiet players | +0.015 |
| holding up decliners | +0.025 |
| ignoring one-game dips | +0.018 |
| demoting sustained risers | **−0.053** |
| newcomers with no prior season | −0.012 |
| stable and too-early players | +0.006 |

The same split explains WR's net +0.022: the QUIET gain there is three times RB's.

### 3. Does adding role awareness improve RB?

**No.**

| RB, C − B | value |
|---|---:|
| capture@10 | +0.0037, CI [−0.005, +0.013] |
| capture@5 | +0.000 |
| capture@20 | +0.003 |

- It is positive in 3 of 5 seasons, and no LOSO fold is significant.
- It does not beat the role-permuted null (+0.003).
- It shows no period pattern: EARLY +0.002, MID +0.009, LATE −0.001.

### 4. Does it preserve the WR improvement?

**Yes.**

- WR capture@10 C − B is −0.002 (CI [−0.013, +0.008]).
- C − A is still **+0.020\*** at capture@10 and **+0.029\*** at capture@5.
- WR Spearman is unchanged.

### 5. What happens to TE?

**Slightly better top 10, slightly worse top 5; neither significant against B.**

- capture@10 +0.007 (+0.011\* against the null), with TE's breakout penalty halved.
- capture@5 −0.010.
- Half-PPR is the same.

### 6. What happens to FLEX?

**No improvement, and a lean the wrong way.**

| FLEX, C − B | value |
|---|---:|
| capture@10 | −0.008 (not significant); every LOSO fold negative, none significant; LATE −0.023\* |
| capture@25 | −0.002 |
| Spearman | +0.0005 |
| capture@5 | +0.001 |

- FLEX capture@10 against current Alpha falls from W10's +0.019\* to **+0.011 (not significant)**.
  capture@20 and @25 still beat A (+0.016\*, +0.012\*).
- No pre-registered FLEX guardrail is breached.

### 7. Does the effect vary by season stage?

**The mechanism's size does not; the role signal's reliability does.**

- The ROLE_UP cost is about −0.05 at RB in every period.
- R strengthens through the season (RB +2.2 → +4.3 touches).
- **The model effect shows no pattern.** The pre-registered hypothesis that role awareness grows
  more useful late was wrong.

### 8. Does Half-PPR agree?

**Yes, on everything:**

- the mechanism is established at every position;
- the verdict is NO EFFECT;
- RB capture@10 C − B is +0.003 and WR −0.002;
- the TE ROLE_UP attribution is +0.010\*;
- R is unchanged.

### 9. Is the role-change signal genuinely useful or just noise?

**It is real information about *roles*, but not usable information about *rankings*.**

**Real:**

- sustained changes persist (R, all positions, all thresholds);
- they mark exactly where historical memory costs capture.

**Not usable:**

- the model gains nothing at RB or WR from being told;
- the role-permuted null performs the same (C − N RB +0.003, WR +0.001).

The information it carries is either already implied by the features Alpha and W10 have (3-game
touches, snap share and last season's level), or it describes the average riser when the loss is
in the rare breakout.

### 10. What is the single best next research question?

> **Does timestamped pre-kickoff information identify which sustained risers are real breakouts?**
> This means the RB risers the historical model demotes and then misses in the top 5: 18 over
> 2021–2025, against 10 for current Alpha.

**W11 shows why this is the question.** The penalty sits in a small, pre-identifiable population
(sustained ROLE_UP players). The repository's pre-Friday usage data cannot separate its breakouts
from its ordinary risers. What could is news the box score does not yet contain:

- a starter ruled out;
- a depth-chart promotion;
- a teammate's injury.

This is the brief's own next step: timestamped weekly information, first for RB. W9 found the
repository's own documented-event coverage too thin to measure (62–91 region player-weeks against
a bar of 100). **W12 therefore needs external timestamped data**, pre-registered against this
specific population.

---

## 4. Decision tree (brief §24)

**"It preserves WR but does not help RB"** (and at RB and WR "it does nothing"):

- **W10 remains useful for WR.** Its gain is intact under arm C and unchanged by any role
  handling.
- **RB needs a different source of information.** Current-role usage already in Alpha's data
  cannot correct the historical-memory problem.
- **Stop broad historical and role modelling.** W11 did not search for another role formulation,
  and should not.
- **Move to timestamped weekly information, first for RB** (Q10).

**Nothing is shipped.** Arm C is not a candidate: it is no better than B, and it gives back some
of B's FLEX top-10 gain.

---

## 5. A priori predictions (§12)

| # | prediction | outcome |
|---|---|---|
| 1 | M1 at RB and WR | ✔ (also TE) |
| 2 | M2 at RB and WR | ✔ (also TE) |
| 3 | M3 at RB | ✗ the opposite sign; history's moves on role changers are *more* often right |
| 4 | R at RB and WR | ✔ +3.5\* and +0.7\* |
| 5 | ROLE_DOWN attribution ≥ 0 | ✔ +0.025\*, +0.013\* |
| 6 | mechanism established, stage 2 runs | ✔ |
| 7 | RB C − B small positive (+0.005 to +0.015) | ~ positive and below the bar, but +0.004 and not significant |
| 8 | WR preserved within ±0.01 | ✔ −0.002 |
| 9 | C − B largest LATE | ✗ no period pattern |
| 10 | verdict PARTIAL | ✗ NO EFFECT |
| 11 | the null arm does nothing | ✔ (G12 passes; FLEX precision@10 −0.019\* is a generic column cost) |
| 12 | Half-PPR agrees | ✔ |

**Eight right, one partly right, three wrong.** The wrong ones share a cause: I expected role
information to help the model, and on average it did not need it.

---

## 6. Validity

**Reproduction first.** W5, W5-E1, W6, the W6 agreement file, W7, W8, the W8 null check, W9, W10
and W10's post-hoc check: **10/10 artifacts byte-identical**. All of W10's gates passed again.

- W10's numbers reproduce exactly: WR capture@10 +0.0223, capture@5 +0.0275, FLEX capture@10
  +0.019, RB +0.000, TE +0.004.

**All twelve gates pass** (`scripts/research/w11_validity_gates.py`):

| gate | result |
|---|---|
| G1 parity | 26,097/26,097 exact |
| G2 role is pre-Friday | 40 weeks rebuilt from rows before the week (11,595 player-weeks): 0 values moved |
| G3 B is W10's arm | 21,330 per-week values (positional and FLEX, Full and Half-PPR, both stages), 0 mismatches |
| G4 no future information | scrambling week *w* onward moves 0 role values for week *w*; the positive control (week *w* + 1 moves) passes 10/10 |
| G5 ECR never a feature | exactly 3 declared training calls: B, C, N; frames from `durable_panel` and `role_panel` only; `role_table` reads only `player_week_stats` |
| G6 walk-forward | 0 leaking frames |
| G7 joins | 0 duplicate keys; current-game count = `games_played_prior` on all 55,093 panel rows; 600/600 independent SQL checks agree |
| G8 order-free | role table identical with input reversed |
| G9 universe / arm A | 24,648 A and ECR values equal W10's, 0 mismatches; 79/79 weeks |
| G10 determinism | both stages byte-identical on re-run (`d9f68424…`, `de7e156c…`) |
| G11 upstream | 10/10 byte-identical |
| G12 null | N − B capture@5/@10 CIs include 0 at RB, WR and TE |

**Amendment A1: a bug found after stage 1 was read.**

- **Symptom.** Stage 1's first output had R empty everywhere.
- **Cause.** The role table stores a transient direction and leaves it missing otherwise. pandas
  turned "missing" into NaN, while the lookup expected `None`.
- **Fix.** A NaN-safe `rolechange.reliability_tag`, with a regression test.
- **Scope.** A field-by-field diff shows the regenerated file differs **only** in R and R's own
  pass/fail flag. Stage 1 was re-gated (G10 included) before R was read.
- **Disclosure.** M1–M3 had been read first; the fix restores R exactly as pre-registered.

**Process notes.**

- Both stages were crash-tested on 2021 alone, reading only structure.
- For the stage-2 crash test, the stage-1 flag was forced on without being read.
- The gate comparisons were checked on that subset first, with 0 mismatches.

---

## 7. Files

| file | role |
|---|---|
| `docs/weekly/W11_PREREGISTRATION.md` | pre-registration and A1 |
| `src/alpha_squad/evaluation/weekly/rolechange.py` | role state and classes, movers, the R tag, ratio-difference bootstrap, both verdicts (23 tests in `tests/unit/test_weekly_rolechange.py`) |
| `scripts/research/w11_mechanism.py` | stage 1: the role table, arm B, M1–M3, R, diagnostics |
| `scripts/research/w11_role_model.py` | stage 2: arms B, C, N |
| `scripts/research/w11_validity_gates.py` | G1–G12 |
| `reports/weekly/w11_mechanism.json`, `reports/weekly/w11_results.json` | every per-week cell and summary |

**Reproduce:**

```
uv run python scripts/research/w11_mechanism.py
uv run python scripts/research/w11_role_model.py
uv run python scripts/research/w11_validity_gates.py --stage 2 --repro-summary <W5-W10 record>
```
