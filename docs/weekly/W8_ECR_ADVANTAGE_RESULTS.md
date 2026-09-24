# W8 — Where does ECR's top-of-board advantage come from?

**Status: COMPLETE.**

**Pre-registered verdict: MIXED**, which maps to recommendation **C (investigate both)**. The
verdict is set by the pre-registered rule and is not changed here. **Only its INFORMATION half is
robust.** The EFFICIENCY half rests on a single WR route that passes by 0.0001 and fails the
pre-registered robustness test.

Run as pre-registered in `docs/weekly/W8_PREREGISTRATION.md`. The pre-registration was committed
at `9fab368` before any ECR-vs-Alpha comparison. The instruments and gates were committed at
`e64ce04` before any result was read. There is one pre-results clarification (amendment A1, the
FLEX matched-pair threshold).

**Research only. Production diff EMPTY. ECR was used as an instrument only.** It trained,
calibrated, tuned and selected nothing. No external data was acquired.

---

## Why does ECR beat Alpha at the top?

**Mostly because ECR knows better who is going to get the ball this week.**

ECR does not know it better from anything Alpha could have read before Friday, and it is not
because ECR is better at predicting what a player does with the ball.

**About 75–94% of ECR's top-10 advantage is opportunity.**

| | share of the advantage that is opportunity |
|---|---:|
| RB | 75% |
| WR | 94% |
| TE | 84% |

The players in ECR's top 10 end up with more targets and carries than the players in Alpha's top
10. More precisely, they get more opportunity than **any** provably-pre-Friday information
forecast. That part alone is larger than ECR's entire lead, at 127% / 142% / 136% of it.

**ECR's top 10 carries *less* forecastable usage than Alpha's.** On forecastable usage alone ECR
is behind:

| | forecastable-usage piece of the gap |
|---|---:|
| RB | −0.012 |
| WR | −0.015 |
| TE | −0.013 |

So ECR is not "weighting the known volume better". Alpha's top 10 already leans harder on the
volume that recent box scores show. ECR's edge is in knowing **when a player will get more (or
less) than his recent usage suggests**.

**What ECR anticipates, measured directly.** Where ECR ranks a player higher than Alpha does,
that player's usage beats its pre-Friday forecast: the rank correlation is **+0.20 at RB, WR and
TE**. It is positive in 65 of 79 weeks at each position, and its CI excludes zero. The same disagreement shows **no relationship at all with
conversion** (+0.01 / +0.02 / +0.01, none significant).

A falsification test run after the results were read (exploratory, labelled below) shows this is
not an artifact of the method. Three boards built only from pre-Friday information disagree with
Alpha too, and in the same direction. None of them gets this bonus; one gets the opposite.

**Efficiency is at most a small WR-specific effect, and it is not robust.** Conversion is
**25% / 6% / 16%** of the gap and never significant at any position. At WR, ECR does order
same-opportunity pairs better, by +0.024. That is exactly the size the pre-registered efficiency
rule needs: 50.2% of the overall pair edge against a 50% bar. It holds in 1 of 5 leave-one-season
-out folds, disappears in Half-PPR, and holds under 2 of 4 bucket definitions.

**One caution about the kind of information this is.** The players behind ECR's repeat wins are
mostly established stars that Alpha drops from its top 10 in some weeks:

| player | weeks ECR had them in its top 10 and Alpha did not (vs the reverse) |
|---|---|
| A.J. Brown | 13 (0) |
| Derrick Henry | 9 (0) |
| Jake Ferguson | 8 (0) |
| T.J. Hockenson | 7 (0) |

That looks more like **durable knowledge of a player's role and quality** than late-breaking
news. W8 cannot tell those two apart, and it is the question that decides whether buying
timestamped news data is worth it (§12).

---

## 0. Reproduction and validity — before any result was read

### 0.1 The foundation reproduces, after one defect was found and fixed

| | result |
|---|---|
| **W6** (and its board-agreement file) | **byte-identical** to the committed results |
| **W7** | **byte-identical** (130,629 numeric leaves) |
| **W5** | **NOT exact on the first re-run.** 45 values of the descriptive field `opponent_pa_prior` moved in the last bit (max 3.6e-15) |

**The W5 defect: found, stopped on, fixed, documented.**

The cause was SQL `avg()` over DOUBLE. DuckDB's parallel hash aggregate combines partial sums in a
planner-chosen order, and floating-point addition is not associative. `snap_prior3` had the same
exposure. W5 had already fixed `stddev_samp` for this reason and missed these two.

**The fix** (`028a72e`, with regression tests): both are now an ordered `list()` reduced with
`math.fsum`, which is exact before its single rounding and therefore independent of input order.

**Verification:**

- **Two post-fix W5 runs are byte-identical.**
- **Two post-fix W5/E1 runs are byte-identical.**

The committed W5 artifacts were regenerated (`5063ccf`). Three reported W5 numbers moved:

- **E1 AUC:** RB 0.4875 → 0.4883, WR 0.4957 → 0.4981. Both are still below chance.
- **The `snap_delta` tercile association:** every CI still contains zero.

**No W5 conclusion changes.** The W5 report carries an erratum block. D113 is untouched
(append-only) and the correction is recorded in D116.

**W8's own inputs never touch the defective code.** W8 reads W7's panel and positional boards,
not W5's context functions. The W8 run is byte-identical to a crash-test run made before the fix.

### 0.2 The eleven gates

The first gate run **failed G5**. Its substring match on `_depth` (meant to catch the depth-chart
view) flagged seven board-depth constants (`region_depth`, `primary_depth`, …). None was a
depth-chart reference; W8 reads no depth-chart data. The matcher now requires a term not to be
preceded by a letter or digit, and it self-tests against must-flag and must-pass lists
(`ee45f83`). **The full suite was re-run, and every result below was read only after it
passed.**

| gate | result |
|---|---|
| **G1** parity | **PASS** — the one-change trainer with no added feature reproduces production 26,097/26,097, max abs diff 0.0 |
| **G2** the forecast is W7's and pre-Friday | **PASS** — 1,422 per-week metrics re-scored from W8's `f` match W7's committed cells exactly; W7's physical-redaction test moves 0 forecast inputs across 2,861 player-weeks |
| **G3** realized opportunity is outcome only | **PASS** — scrambling the predicted season's realized usage changes 0 forecasts; the runner feeds realized usage to exactly one model, the Class D arm |
| **G4** ECR is not in Alpha | **PASS** — no ECR/market/rank token in Alpha's features, and no ECR in any training frame |
| **G5** no post-Friday news | **PASS** (after the fix above) — the matcher self-test passes; 0 forbidden identifiers |
| **G6** no realized information in predictors | **PASS** — covered by G2 and G3 |
| **G7** walk-forward | **PASS** — 0 training frames contain the predicted season |
| **G8** joins and identity | **PASS** — 0 duplicate keys; max `\|G − (G_F+G_S+G_C)\|` = **2.6e-16**; the runner also aborts on any capture mismatch, any attribution that does not sum to `G`, or any missing usage row with opportunity |
| **G9** universe and cutoff | **PASS** — 5,930 / 9,378 / 4,742 player-weeks, identical to W7; `CF_A`, `ECR` and `ORACLE_USAGE` re-score to W7's committed cells (12,798 metrics, 0 mismatches); 0 kicked-off players |
| **G10** determinism | **PASS** — byte-identical re-run (`3911d5da…`) |
| **G11** upstream | **PASS** — §0.1 |

**The foundation is unchanged from W2–W7:** 79 weeks, the Friday cutoff, the universe,
Full-PPR primary, the ECR series, and week-paired testing. Every number here is paired within
week and resampled over weeks.

---

## 1. The decomposition

For every player-week:

    points = forecastable usage (f) + usage surprise (s) + conversion (c)

- **`f`** is W7's Class A forecast.
- **`s`** is usage beyond that forecast.
- **`c`** is points beyond what the usage was worth (W5's definition).

ECR's capture@k lead over Alpha splits **exactly** into the same three pieces, because the
capture denominator is common to both boards.

### Positional capture@10, 79 weeks

| | RB | WR | TE |
|---|---|---|---|
| **ECR − Alpha (`G`)** | **+0.0228\*** [+0.0039, +0.0436] | **+0.0320\*** [+0.0112, +0.0532] | **+0.0258\*** [+0.0083, +0.0436] |
| forecastable usage `G_F` | **−0.0120\*** (13–62) | **−0.0154\*** (7–72) | **−0.0133\*** (13–66) |
| **usage surprise `G_S`** | **+0.0290\*** (53–22), **127%** | **+0.0453\*** (61–18), **142%** | **+0.0350\*** (57–22), **136%** |
| conversion `G_C` | +0.0057 (42–33), 25% | +0.0021 (42–37), 6% | +0.0041 (41–38), 16% |
| **all opportunity (`G_F + G_S`)** | **+0.0171, 75%** | **+0.0299, 94%** | **+0.0217, 84%** |

In the win–loss counts (W–L), a "win" is a week in which the piece favours ECR. The pattern is the
same at capture@5 and capture@20 at every position (RB capture@5's total gap is itself
non-significant).

### How to read the pieces

- **`G_F` is negative everywhere, in 62–72 of 79 weeks.** ECR's top 10 has *less* opportunity
  that recent usage forecasts. Alpha's top leans harder on known volume, consistent with W5's
  "Alpha ranks by floor".
- **`G_S` is larger than the whole gap everywhere.** ECR's top 10 receives more opportunity than
  pre-Friday information predicted, by more than enough to overcome its forecastable-usage
  deficit.
- **`G_C` is never significant.** At RB/WR/TE, ECR's top 10 does not convert opportunity
  measurably better.

---

## 2. Q1 — how much of the advantage occurs when opportunity is unexpectedly different?

**Nearly all of it.** Players whose usage landed in the top third of surprise are about a third
of the players the two top-10s disagree on. They carry most of ECR's capture@10 lead:

| | LARGE-surprise share of swapped players | LARGE-surprise share of ECR's lead |
|---|---:|---:|
| RB | 36% | **84%** (+0.0192) |
| WR | 36% | **107%** (+0.0342) |
| TE | 35% | **78%** (+0.0201) |

**Split by direction:**

| | LARGE_UP (more usage than forecast) | LARGE_DOWN (usage collapsed) |
|---|---:|---:|
| RB | **+0.0262\*** | −0.0070\* |
| WR | **+0.0436\*** | −0.0094\* |
| TE | **+0.0284\*** | −0.0083\* |

Two things drive the lead:

- ECR puts players who will **out-earn their forecast** into its top 10 (LARGE_UP), and that is
  the larger part.
- The small negative LARGE_DOWN attribution means players whose usage **collapsed** sit
  disproportionately in Alpha's exclusive top 10. Their remaining points count for Alpha; the
  cost of including them shows up as the LARGE_UP points ECR took instead.

**By pairs.** ECR's top-region pairwise edge is largest on pairs where at least one player's
usage surprised:

| pair type | RB | WR | TE |
|---|---|---|---|
| all region pairs `Ω` | +0.0311\* | +0.0476\* | +0.0223\* |
| **SURPRISE** pairs | **+0.0497\*** | **+0.0651\*** | **+0.0459\*** |
| CLOSE pairs (both usages close to forecast) | +0.0154 | **+0.0411\*** | **−0.0585\*** |
| MATCHED pairs (equal realized usage) | +0.0058 | **+0.0239\*** | −0.0035 |
| SURPRISE − CLOSE | +0.0343 (p = 0.059) | +0.0241 | **+0.1043\*** |

---

## 3. Q2 — how much remains when opportunity was predictable?

**At RB and TE, none. At WR, some.**

- **Capture attribution to CLOSE-bucket players** is ≈ 0 everywhere: +0.0018 / −0.0022 /
  +0.0037.
- **CLOSE pairs:**
  - RB: +0.0154, not significant (half the overall edge).
  - **TE: Alpha is significantly *better*** (−0.0585, 42 of 61 decided weeks).
  - **WR: ECR keeps a real edge** (+0.0411\*, 86% of its overall pair edge).

The WR close-pair edge is where the efficiency hypothesis lives. §8 explains why it does not
survive the robustness checks.

---

## 4. Q3 — how much disappears if Alpha had perfect opportunity information?

There are two ways to answer this, and they give very different numbers. That difference was
predicted before the run and fixed in the pre-registration (§6).

### The pre-registered reading

This is the part of ECR's lead that is **not** opportunity, i.e. what would survive perfect
opportunity knowledge.

| | RB | WR | TE |
|---|---|---|---|
| conversion `G_C` (share of `G`) | 25%, n.s. | 6%, n.s. | 16%, n.s. |
| MATCHED-pair edge (share of `Ω`) | 19%, n.s. | **50%\*** | −16%, n.s. |

**So roughly 75–94% of ECR's capture lead disappears if opportunity is known.** At WR, about half
of its *pairwise* edge on equal-opportunity pairs remains.

### The naive counterfactual (reported, not in the verdict)

`ALPHA_ORACLE_OPP` is production's model retrained with the week's own realized usage. It is a
Class D diagnostic, never deployable.

| capture@10 | RB | WR | TE |
|---|---:|---:|---:|
| B − A (Alpha + perfect opportunity vs Alpha) | +0.181\* | +0.199\* | +0.195\* |
| C − A (ECR vs Alpha) | +0.023\* | +0.032\* | +0.026\* |
| **C − B** | **−0.159\*** | **−0.167\*** | **−0.169\*** |
| (B − A) / (C − A) | 8.0× | 6.2× | 7.5× |

Perfect opportunity knowledge beats ECR by six to eight times ECR's entire lead, exactly as
predicted (prediction 5). It "closes the gap" whether or not ECR's lead is about opportunity. It
contains in-game injuries and game script that nobody knows on Friday. That is why the
pre-registration kept it out of the verdict.

---

## 5. Is it an artifact? (exploratory, post-hoc — excluded from the verdict)

Because `s = x − f`, a board that prefers players the forecast under-rates shows a negative
`G_F`. If those players merely regress to their forecast, it could show a mechanically positive
`G_S`.

**The test.** Decompose boards built from Class A information only against Alpha, using the same
instrument. They cannot know this week's surprise.

| board vs Alpha (capture@10) | ρ(d, f) | ρ(d, s) | `G_S` |
|---|---|---|---|
| **LAST3_POINTS** (points per game, last 3) — disagrees with Alpha the way ECR does | **−0.30 / −0.33 / −0.32** | −0.03 / **−0.07\*** / **−0.09\*** | −0.000 / **−0.015\*** / −0.012 |
| FORECAST_USAGE (rank by `f`) | +0.28 / +0.31 / +0.25 | −0.07\* / −0.02 / −0.02 | −0.002 / −0.008 / −0.004 |
| ALPHA_PLUS_OPP (W7's Class A arm) | +0.16 / +0.07 / +0.08 | −0.03 / −0.04 / +0.01 | +0.001 / −0.007 / +0.002 |
| **ECR** | **−0.20 / −0.26 / −0.14** | **+0.20\* / +0.20\* / +0.19\*** | **+0.029\* / +0.045\* / +0.035\*** |

Values are RB / WR / TE.

**No Class A board gets an unforecast-usage bonus from disagreeing with Alpha.** The one that
disagrees exactly as ECR does (preferring lower-forecast players) gets a *negative* one. ECR's
`G_S` is therefore not produced by the method. ECR anticipates usage that provably-pre-Friday
information does not. `reports/weekly/w8_null_check.json` holds this check (byte-identical on
re-run).

---

## 6. Q4/Q5 — is the remaining gap opportunity, efficiency or both, and does it differ by position?

| | pre-registered verdict | routes that hold | the evidence in one line |
|---|---|---|---|
| **RB** | **INFORMATION** | I-2 | usage surprise is 127% of the gap; conversion n.s.; close and matched pairs n.s. |
| **WR** | **MIXED** | I-2, E-1, E-2b | usage surprise is 142% of the gap, **and** ECR keeps an edge on close pairs (+0.041\*) and matched pairs (+0.024\*); conversion in capture terms n.s. (6%) |
| **TE** | **INFORMATION** | I-1, I-2 | the cleanest case: SURPRISE − CLOSE +0.104\*, and on close pairs Alpha is *better* |
| **FLEX** | **INFORMATION** | I-2 | §7 |

**Overall, by the pre-registered combination rule: MIXED**, because MIXED at either RB or WR
makes the overall MIXED.

- **RB and TE:** the gap is information about usage.
- **WR:** the gap is mostly information about usage, plus a smaller, fragile efficiency edge.

**No W flag at any position.** Forecastable-usage weighting runs *against* ECR, not for it.

---

## 7. Q6 — FLEX

| FLEX | capture@10 | capture@25 |
|---|---|---|
| ECR − Alpha | **+0.0388\*** | **+0.0272\*** |
| `G_F` | −0.0147\* | −0.0114\* |
| `G_S` | **+0.0377\*** (97%) | **+0.0344\*** (127%) |
| `G_C` | **+0.0158\*** (41%) | +0.0042 (15%) |

FLEX pairs: all +0.0457\*; SURPRISE +0.0642\*; CLOSE +0.0334 (p = 0.066); MATCHED +0.0191\*.
**Verdict: INFORMATION.**

The same pattern holds. There is one FLEX-only feature: a **significant conversion piece at
capture@10** (+0.016, 41%) that no single position has and that vanishes by capture@25. It is the
cross-position part of FLEX, meaning which position's top players convert better. It is recorded,
not interpreted: W4/D112 already settled that cross-position calibration is not Alpha's lever.

---

## 8. Robustness — pre-registered §9, counted mechanically

A route counts as **robust** if it holds in at least 4 of 5 leave-one-season-out folds, in
Half-PPR, and under at least 3 of the 4 bucket/metric variants.

| | LOSO folds | Half-PPR | variants | robust? |
|---|---|---|---|---|
| **WR — INFORMATION** | 5/5 | yes | 4/4 | **YES** |
| **TE — INFORMATION** | 5/5 | yes | 4/4 | **YES** |
| **RB — INFORMATION** | 3/5 | yes | 4/4 | **no, narrowly** |
| **WR — EFFICIENCY** | **1/5** | **no** | **2/4** | **NO** |
| RB — EFFICIENCY | 0/5 | no | 0/4 | no |
| TE — EFFICIENCY | 0/5 | no | 0/4 | no |

- **RB information misses robustness narrowly.** The folds that fail are "drop 2024" and
  "drop 2025", and they fail because RB's *total* gap loses significance there (+0.0193,
  +0.0211). The `G_S` piece is significant in **all five** folds.
- **WR efficiency is fragile in every sense.**
  - E-2b needs `Ω_match ≥ ½ Ω`: 0.0239 against 0.0238.
  - The WR close-pair edge's per-season values range from −0.039 to +0.083.
  - **Half-PPR turns WR into INFORMATION**: its close-pair CI crosses zero.

**The component pieces are strikingly stable.** Across all five LOSO folds at every position:

- `G_F` is significantly negative;
- `G_S` is significantly positive;
- `G_C` is never significant.

**Half-PPR replicates everything:** RB, WR, TE and FLEX are all INFORMATION, and the Half-PPR
overall verdict is INFORMATION. Half-PPR never selects.

**Depth:** capture@20 gives the same verdicts. At capture@5, RB's own gap is not significant, so
RB is inconclusive there.

---

## 9. Player level (descriptive — no inference)

| position / group | mean `d` (ranks) | usage surprise `s` | conversion `c` | forecast `f` | team EPA (last 3) | games prior |
|---|---:|---:|---:|---:|---:|---:|
| RB — ECR-favoured (top decile) | +6.7 | **+1.30** | +0.57 | 13.17 | **+1.97** | 7.4 |
| RB — Alpha-favoured (bottom decile) | −7.6 | **−0.93** | +0.02 | 13.56 | −1.02 | 5.9 |
| WR — ECR-favoured | +11.9 | **+1.35** | +0.54 | 12.74 | **+2.48** | 6.1 |
| WR — Alpha-favoured | −14.1 | **−0.52** | −0.63 | 13.20 | +0.25 | 6.0 |
| TE — ECR-favoured | +6.4 | **+0.42** | +1.05 | 8.32 | **+3.50** | 7.2 |
| TE — Alpha-favoured | −5.0 | **−1.19** | −0.15 | 8.83 | +0.13 | 6.7 |

**What separates the groups:**

- **Usage surprise, at every position.** ECR's favourites get more usage than forecast; Alpha's
  favourites get less.
- **ECR's favourites carry a lower forecast `f`.** Alpha prefers the higher recent volume.
- **ECR favours players on better offenses** (team EPA), even though team EPA is one of Alpha's
  own features.
- **Role volatility and history do not separate the groups consistently.** That was prediction
  10's mechanism, and it is wrong.

**Repeat hits** are weeks a player finished top-10, in one board's top 10 but not the other's.
ECR-only hits outnumber Alpha-only hits at every position:

| | ECR-only | Alpha-only |
|---|---:|---:|
| RB | 78 | 47 |
| WR | 83 | 54 |
| TE | 71 | 48 |

The players with the most net ECR-only hits are overwhelmingly established stars:

- **WR:** A.J. Brown 13–0, Tyreek Hill 5–0, Davante Adams 5–1, Justin Jefferson 4–0, Ja'Marr
  Chase 4–0.
- **RB:** Derrick Henry 9–0, Jahmyr Gibbs 7–1, Nick Chubb 5–0.
- **TE:** Jake Ferguson 8–0, T.J. Hockenson 7–0.

Their mean usage surprise is mostly positive. ECR keeps them in its top 10 in weeks Alpha
demotes them, typically after a quiet stretch in the lagged box scores, and they then get their
usual usage.

That is a **hypothesis about the kind of information**, not a finding: durable knowledge of role
and quality, rather than late-breaking news.

---

## 10. The a priori predictions, scored

| # | prediction | outcome |
|---|---|---|
| 1 | RB: `G_S` largest, ≥ ⅓ `G`, significant | **right** (127%) |
| 2 | WR: `G_C` largest | **wrong** — WR has the *smallest* conversion share (6%) and the largest surprise share (142%) |
| 3 | `G_F` small (< ⅓ `G`) at RB, WR | **partly** — below ⅓ in the letter, but large and **negative** (≈ −50%), which I did not anticipate |
| 4 | `Ω_close` > 0 at both; < ½ `Ω` at RB, ≥ ½ `Ω` at WR | **mostly right** — the shares are as predicted; RB's `Ω_close` is positive but not significant |
| 5 | B beats ECR by ≥ +0.10 capture@10 everywhere | **right** (+0.16 to +0.17) |
| 6 | `ρ(d, s)` > 0 at RB, weaker at WR; `ρ(d, c)` > 0 at WR | **partly** — RB right; WR is *equal* (+0.20), and `ρ(d, c)` at WR is ≈ 0 |
| 7 | TE inconclusive | **wrong** — TE is the cleanest INFORMATION case |
| 8 | overall MIXED: INFORMATION at RB, EFFICIENCY at WR | **partly** — the label is right, the mechanism wrong: WR is MIXED through information plus a knife-edge efficiency pass |
| 9 | FLEX MIXED | **wrong** — INFORMATION |
| 10 | ECR-favoured: positive `s`, more volatile roles, shorter histories | **partly** — positive `s` right; the role and history differences are absent or reversed |

**Two right, five partly right, three wrong.**

The errors point one way. I expected expert judgement to show up as *efficiency*, especially at
WR. It shows up as *anticipated usage* at every position.

---

## 11. Answers

1. **How much of ECR's advantage occurs when opportunity was unexpectedly different?** Most of it.
   - Players with large usage surprises are ~36% of the disagreements but carry **78–107%** of
     ECR's capture@10 lead.
   - ECR's pair edge on SURPRISE pairs is 1.4–2.1× its overall edge.
2. **How much remains when opportunity was predictable?**
   - **RB:** none (n.s.).
   - **TE:** none — Alpha is better on close pairs.
   - **WR:** some. A pair edge of +0.041 on close pairs, but not in capture terms, and not
     robustly.
3. **How much disappears with perfect opportunity information?** **About 75% (RB), 94% (WR) and
   84% (TE)** of the capture@10 lead is opportunity. The rest (conversion) is never significant.
   The naive "Alpha + perfect opportunity" board beats ECR by 6–8× ECR's lead, and it proves
   nothing about ECR, as pre-registered.
4. **Is the gap opportunity, efficiency, both, or inconclusive?**
   - **Pre-registered verdict: MIXED.**
   - **Robust evidence: opportunity information.** Specifically, usage that no provably-pre-Friday
     information forecasts. It survives a falsification test that Class A boards fail.
   - **Efficiency:** at most a small, non-robust WR effect.
5. **Does it differ by position?** Only in the degree of efficiency.
   - **TE:** information alone, the cleanest case.
   - **RB:** information, with RB's overall gap itself marginal.
   - **WR:** information plus a fragile efficiency edge.
6. **Does FLEX show the same thing?** Yes — **INFORMATION**, with one cross-position conversion
   piece at capture@10 that disappears by capture@25.
7. **How confident are we?**
   - **High** that ECR's top-10 advantage is mainly about **opportunity it anticipates beyond
     pre-Friday data**. Every piece is stable across seasons and scoring, the decomposition is
     exact, and the falsification test fails for every Class A board.
   - **Low** that there is a real efficiency advantage.
   - **Not established:** *what kind* of information ECR has, late-breaking news or durable
     knowledge of role and quality. The player-level pattern hints at the latter; nothing here
     tests it.
8. **The single best next research question** — §12.

---

## 12. Recommendation and the next question

**By the pre-registered mapping, MIXED → C: investigate both.**

**By the evidence, the two halves are not equal:**

- **The information half is robust at WR and TE, and holds at RB** in every piece.
- **The efficiency half is one WR route that passes by 0.0001** and fails the pre-registered
  robustness test.

So C should be read as **information first**, with efficiency at WR as a low-priority follow-up,
not an equal second track.

Direction A as the brief phrases it — *acquire timestamped external information* — is **premature
by one measurement**. Everything above says ECR knows this week's usage better than pre-Friday
box scores do. Nothing says that knowledge is **late-breaking**. If it is durable knowledge of a
player's role and quality, available before the season, then a news-data project would buy the
wrong thing.

**The single best next question:**

> **Is ECR's usage edge durable (knowable from pre-season role/quality information) or
> late-breaking (week-specific news)?**

Concretely:

1. Take ECR's anticipation statistic (`ρ(d, s)`, and `G_S`).
2. Measure how much of it is absorbed by conditioning on two sources that already exist in the
   repository and need no acquisition:
   - **a durable prior:** the player's prior-season role and rank. This is Class A, published
     before the season, and not among W7's in-season features. W5 found it carries the largest
     top-of-board lift of anything it tested.
   - **the week's teammate availability:** the Friday injury report. This is Class B; W5 found
     it the only injury signal with any lift, at RB.

It is a measurement, not a model. It reuses W8's instruments.

**Either answer decides the next investment:**

- **Mostly durable:** the missing information is cheap and already present. Stop, and bring it to
  the user as a candidate for a controlled Alpha experiment.
- **Mostly late-breaking:** direction A is justified, and data acquisition becomes an explicit
  decision for the user.

---

## Appendix — scope and reproducibility

**Instruments:**

- `src/alpha_squad/evaluation/weekly/advantage.py`: the decomposition, buckets, pair tests and
  the §7 verdict rules. 94 unit tests.
- `scripts/research/w8_ecr_advantage.py`: the runner.
- `scripts/research/w8_validity_gates.py`: G1–G11.
- `scripts/research/w8_null_check.py`: the exploratory falsification test.

**Results:** `reports/weekly/w8_results.json`, `reports/weekly/w8_null_check.json`. Both are
byte-identical on re-run.

**W5 determinism fix:**

- `evaluation/weekly/context.py::_exact_mean`, plus two regression tests;
- regenerated `reports/weekly/w5_results.json` and `reports/weekly/w5_e1.json`.

**Statistics:** 79 weeks, paired within week; bootstrap over weeks (10,000 resamples, seeds 0–9);
Wilcoxon; win/loss counts. Players are never treated as independent observations.

**Scope:** research only. The production diff is empty. ECR trained, calibrated, tuned and
selected nothing. No external data was acquired. Alpha was not changed.
