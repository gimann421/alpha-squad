# Project State

Living summary of what is implemented, validated, and outstanding. Updated at the end of every
milestone. See `docs/TRACEABILITY.md` for the acceptance-criteria-level mapping.

## Status: W8 complete (D116) — **ECR's top-of-board advantage is anticipated OPPORTUNITY, not efficiency. Pre-registered verdict MIXED (recommendation C), but only its information half is robust. Nothing shipped.**

Research only. ECR is used as an instrument, never a feature. No data acquired, Alpha unchanged,
production diff EMPTY. **Entry point: `docs/weekly/W8_ECR_ADVANTAGE_RESULTS.md`.**

### CURRENT WEEKLY RESEARCH STATUS

- **The exact decomposition of ECR's capture@10 lead** (identity residual 2.6e-16), RB / WR / TE:
  - lead: +0.0228\* / +0.0320\* / +0.0258\*
  - **all opportunity: 75% / 94% / 84%**
  - conversion: 25% / 6% / 16%, never significant
- **ECR's top 10 carries LESS forecastable usage than Alpha's** (`G_F` −0.012 to −0.015\*) and much
  more **unforecast** usage (`G_S` +0.029 to +0.045\*, 127–142% of the lead).
- **ECR's disagreements with Alpha track usage surprise, not conversion:** ρ(d, s) is +0.20\* at
  every position; ρ(d, c) ≈ 0.
- **Large-surprise players** are ~36% of the disagreements and carry **78–107%** of the lead.
  On close-to-forecast pairs, ECR's edge is not significant at RB, Alpha is **better** at TE, and
  ECR keeps +0.041\* at WR.
- **Falsification (exploratory):** Class-A-only boards that disagree with Alpha the same way get no
  such bonus. LAST3_POINTS: `G_S` ≤ 0, ρ(d, s) −0.03 to −0.09. ECR's `G_S` is not produced by the
  method.
- **Verdicts:** RB INFORMATION · WR MIXED · TE INFORMATION · FLEX INFORMATION → **overall MIXED**.
  - **Robust** (≥ 4/5 LOSO, Half-PPR, ≥ 3/4 variants): information at WR and TE; RB narrowly
    misses on LOSO because its total gap is marginal.
  - **Not robust:** WR efficiency (1/5 LOSO, fails Half-PPR, 2/4 variants; passes by 0.0001).
  - Half-PPR: INFORMATION everywhere.
- **The naive "Alpha + perfect opportunity" board** beats ECR by 6–8× ECR's lead. It is
  uninformative, as pre-registered, and kept out of the verdict.
- **Player level:** ECR's repeat top-10 wins are established stars Alpha demotes after quiet weeks
  (A.J. Brown 13–0, Derrick Henry 9–0, Jake Ferguson 8–0). This is a hypothesis of durable
  role/quality knowledge, not late news.
- **W5 determinism defect found and fixed:** SQL `avg()` over DOUBLE, max 3.6e-15. W5 is now
  byte-stable. E1 AUC RB 0.4883 / WR 0.4981 (were 0.4875 / 0.4957); no conclusion changes.
- **Methodology:** 11 gates pass. G5 failed first on a false positive and was fixed and re-run
  before any result was read. W6/W7 are byte-identical. Predictions: 2 right, 5 partly right,
  3 wrong.
- **Next: W9** — is ECR's usage edge **durable** (prior-season role/rank, already in the repository)
  or **late-breaking** (Friday news)? That decides whether direction A's data acquisition is
  warranted at all.

### Earlier status: W7 complete (D115) — **Pre-Friday opportunity is only partly predictable, mostly already in Alpha, and does not improve the top of the board. Verdict HARM by the pre-registered order (= NO EFFECT in the brief's scheme). Nothing shipped.**

Research only. No ECR, no change to Alpha's ranking model. Entry point:
`docs/weekly/W7_OPPORTUNITY_RESULTS.md`.

- **Opportunity is partly predictable.** The best Class A (provably pre-Friday) forecast of
  week-*w* usage-expected points ranks it at per-week Spearman **0.709 (RB) / 0.672 (WR) / 0.625
  (TE)**, with pooled R² 0.48 / 0.42 / 0.39. That is above Alpha's points board (0.668 / 0.636 /
  0.576), but far from known.
- **Alpha already holds ~84–86% of it.** Alpha's 11 features alone reach 0.699 / 0.660 / 0.612.
  All genuinely new Class A information adds **+0.0105 / +0.0118 / +0.0127**. Each is
  significant, and all are below the +0.02 bar (**C1 fails everywhere**).
- **The double-counting control:** net of 5-game re-expressions, the gain is +0.0096 at RB (new),
  +0.0052 at WR (about half re-expression) and +0.0044 at TE (not distinguishable from
  re-expression).
- **The information is the limit, not the model.** Ridge ≈ CatBoost (CatBoost is worse at TE).
  Class B lagged xFP adds **0.0000**.
- **Not at the top.** Within Alpha's top 5, the forecast's rank correlation with realized
  opportunity is **0.12–0.30**. New information leaves it unchanged at RB (0.124 → 0.124) and
  lowers it at WR (0.195 → 0.165). It helps bands 6–50.
- **Alpha + pre-Friday opportunity (one change) vs production:**
  - RB capture@10 +0.0047 (null).
  - **WR capture@10 −0.0127 CI[−0.0250, −0.0006]**, negative in every LOSO fold and season, and
    replicated in Half-PPR.
  - TE −0.0033 (null).
  - Whole-board Spearman +0.004–0.011.
  - The W5 cliff does not shrink (WR −0.0800 → −0.0963).
- **The perfect-opportunity prize is not reachable on Friday.** Realistic forecasting recovers
  +2.6% (RB), −6.3% (WR) and −1.7% (TE) of `ORACLE_USAGE`'s capture@10 advantage.
- **Predictions:** 4 right, 3 partly right, 3 wrong. Most consequential: WR was predicted null
  and was harmed.
- **Methodology:** eleven gates.
  - G1: 26,097/26,097 exact parity.
  - G2: a physical-redaction leakage test that moves 0 predictor values.
  - W5/W6 re-run first.
- **Next:** *Is ECR's top-of-board edge over Alpha concentrated in the player-weeks whose
  opportunity departs from its pre-Friday forecast?* This asks whether the expert edge is news
  about usage or judgement about efficiency. It is a measurement using W7's residual; ECR is a
  diagnostic only.

### Earlier status: W6 complete (D114) — **Training for higher-end outcomes does NOT fix the top of the board. Verdict NO EFFECT. The objective barely controls the ordering — the features do. Nothing shipped.**

Research only. One argument changed (the CatBoost loss). Entry point:
`docs/weekly/W6_UPPER_OUTCOME_RESULTS.md`.

- **Verdict NO EFFECT.** `B2_Q70` (70th-percentile target) vs the production control, 79 weeks:
  RB capture@5 **+0.0023** CI[−0.0124,+0.0173], RB capture@10 **+0.0052** CI[−0.0022,+0.0135],
  WR capture@5 **−0.0008**, WR capture@10 **−0.0051**. **Every primary CI contains zero** against
  a +0.02 threshold and a measured MDE of ~0.02.
- **The median weekly difference is exactly 0.0000** at both positions; the two boards produce an
  identical capture@10 in **32 of 79 RB weeks**.
- **The W5 cliff did NOT shrink** (the mechanism check): RB −0.0710 → **−0.0650** (8%, inside
  noise; Q60 *widens* it); WR −0.0800 → **−0.0836**, worse, and monotonically worse with quantile.
- **THE EXPLANATION, and the constraint it adds:** the target change moves the predicted numbers
  enormously (RB mean prediction +48%, 6.86 → 10.18) and the **ordering almost not at all** —
  board rank correlation with the control is **0.9958 / 0.9963 / 0.9912** (RB/WR/TE), top-10
  overlap 89–93%, and the top 10 is **literally identical in 24–41% of weeks**. On these 11 lagged
  features the quantile is very nearly a **monotone rescaling**, which cannot change any ranking.
  **The ordering is determined by the features, not by the objective.**
- **No dose-response**, and `B0_RMSE` (the discriminating control) is indistinguishable from
  `B2_Q70` — moving off MAE in *any* direction does the same amount of nothing.
- **One genuine positive, off-target:** TE capture@5 **+0.0208** CI[+0.0068,+0.0367], p=0.015,
  replicated at every quantile and in Half-PPR, passing all three genuineness checks. Not a primary
  cell, does not propagate to TE capture@10, and lands on the one position W5 found had no cliff.
- **Not more bust-prone either**: top-10 false-positive rate RB 26.5%→26.1%, WR 42.9%→43.2%. The
  change is neither better nor recklessly extreme. It is inert.
- **A defect in W6's own pre-registration, disclosed** (amendment A1): the HARM clause had no
  practical floor, so two negligible guardrail breaches (RB capture@50 −0.0029, FLEX Spearman
  −0.0014) trigger it literally. NO EFFECT is reported; both readings recommend the same action.
- **Second consecutive phase to rule out reshaping the existing signal** — D112 ruled out
  cross-position calibration, D114 rules out target reshaping.
- **Methodology**: nine gates pass. **G1 load-bearing** — retraining with production's own loss
  reproduces production's own stored predictions **exactly** (29,376/29,376, max abs diff 0.0), so
  every arm differs from production in one argument. W3/W4/W5 reproduce exactly; output
  byte-identical on a repeat run. **Four of eight a priori predictions were wrong.**
- **Next: W7** — *how much of a player's week-w opportunity (targets and carries) is actually
  forecastable from Friday information?* W5 showed perfect opportunity foresight is worth 53–63%
  of the whole ceiling and would beat ECR by +0.16 to +0.21. **It is a measurement, not a model**,
  and it should be asked before anything else is built.

### Earlier status: W5 complete (D113) — **The top-of-board "collapse" is range restriction, but a REAL cliff sits underneath it at RB and WR (not TE). No pre-cutoff information class is material.**

Research only. Entry point: `docs/weekly/W5_TOPBOARD_FORENSICS.md`.

- D112's "corr collapses to RB 0.251 / WR 0.222 / TE 0.141" is fully explained by range
  restriction: a same-Spearman ranker with no top defect scores **0.151 / 0.110 / 0.142**.
- **Real cliff on capture@10**: RB −0.0710, WR −0.0800, TE −0.0096 (**no cliff at TE**).
- **Alpha ranks by FLOOR; the top-10 is won by CEILING.** Misses sit at median predicted rank
  22/29/20; 62–83% of missed regret is prior-week starters it already ranks.
- **No information class is material** — injury (STRICT coverage 0.2%), depth chart, role change,
  team environment, matchup (5–10% of missed regret).
- **Misses are NOT predictable** where the cliff is: AUC 0.4883 (RB), 0.4981 (WR) (D116 erratum).
- **`ORACLE_USAGE` recovers 53–63% of the ceiling** and beats ECR by +0.159 to +0.206.

### Earlier status: W4 complete (D112) — **Cross-position calibration is NOT the FLEX bottleneck (verdict D). A PERFECT cross-position scale buys 2.1% of the available headroom. Do not build calibration. Nothing shipped.**

Research only. Entry point: `docs/weekly/W4_FLEX_FORENSICS_RESULTS.md`.

- **Verdict D.** FLEX capture@10: `X` (perfect cross-position scale) = **+0.0075, CI
  [−0.0055,+0.0205]**, 0.58x MDE. `W` (perfect within-position order) = **+0.3613**, 79-0 weeks.
  `X/W` = **2.1%**.
- A perfect cross-position scale still loses to ECR (**−0.0313**); a perfect within-position order
  beats ECR by **+0.3225**.
- **Four pre-registered causal calibrations, none succeeded**; harm rises with aggressiveness.
- The exact additive decomposition: Alpha orders cross-position pairs *better* (0.7385) than
  within-position pairs (0.7365) — **the premise had the wrong sign**.
- **Composition matching is NOT ranking quality**; **Alpha's anti-TE bias is real, removable and
  NOT an error** (ECR, which beats Alpha everywhere, has a stronger one).
- ~~W3's "pooling destroys ~84%"~~ **superseded**; the oracle that removes every pooling effect
  recovers 2.1%.
- **W5 note:** D112's conditional-correlation figures are correct as measurements but were
  over-read as a diagnosis — see D113.

### Earlier status: W3 complete (D111) — **Alpha has REAL weekly ranking signal (~53% of ECR's edge over a trivial baseline) but ZERO edge at the FLEX top 10, loses to ECR on every board, and cannot produce a Friday board at all. Nothing shipped.**

Evaluation only. **No model built, tuned or modified; no ECR added; no feature added;
production diff EMPTY.** Entry point: `docs/weekly/W3_ALPHA_BENCHMARK_RESULTS.md`.

- **Alpha's signal is a DEEP-BOARD signal.** FLEX vs season-to-date baseline: Spearman
  **+0.0347** (2.4x MDE, **68-11 weeks**, p=3e-12) but **capture@10 +0.0027** (0.16x MDE,
  **39-40 weeks**, p=0.78). Monotone gradient: @50 1.69x -> @25 0.82x -> @10 0.16x.
- **Alpha loses to ECR everywhere** (FLEX Spearman −0.0313, **5.15x MDE**, 8-71 weeks). Order is
  identical on every board: **ECR > Alpha > B0 > B1**. The product gate is not met.
- **W2 reproduced exactly**: ECR−B0 on FLEX = **+0.0660** vs W2's +0.066. Instrument is stable.
- ~~**Pooling destroys ~84% of Alpha's positional top-10 signal.**~~ **SUPERSEDED by W4/D112** —
  the causal version of this claim does not hold; the oracle that removes every pooling effect
  recovers 2.1%. The *descriptive* part stands: Alpha's FLEX top-10 is **1.4% TE** against a
  realized 10.8% and over-represents RB by +15.3pp, but W4 shows correcting that buys nothing.
- **Cross-position calibration does NOT explain the overall deficit**: Alpha's within-position
  deficit to ECR (−0.0348) equals its pooled deficit (−0.0313). W4 confirmed and extended this.
- **The model cannot produce a real Friday board** — `player_week_features` exists only for
  players who PLAYED, so Alpha can only score retrospectively. Blocking product limitation.
- **A live leakage defect in the SERVED path**: the evidence layer reads the final injury report
  with no `date_modified` filter; 7.2-9.8% of the Out/Doubtful rows it consumes were finalised
  after Friday, and the 2025 file has no such column at all. Excluded from W3/W4; must be fixed.
- **Secondary, and a trap**: Alpha under-predicts by a near-constant −1.0 to −1.4 across all ten
  deciles — a pure additive shift that **cannot change any ranking**. The most obvious-looking
  defect is the least worth fixing.
- **Positional shares of ECR's Spearman edge**: TE 60%, WR 54%, FLEX 53%, RB 42%, **QB 25%**
  (barely above the noise floor). Alpha is materially **more stable** than the baseline
  (FLEX SD 0.050 vs 0.096, close to ECR's 0.042).

### Earlier status: W1.1 + W2 complete (D110) — **W1's FLEX and Half-PPR findings were WRONG and are corrected at source: FantasyPros DOES publish a historical weekly RB/WR/TE FLEX board. The ECR benchmark is established and the weekly noise floor is measured. Nothing shipped.**

Audit, benchmark and pre-registration only. **No Alpha model built, fitted or compared;
`models/`, `league/`, `api/`, `cli.py`, `market/consensus.py` and configs untouched.**
**Entry points: `docs/weekly/W11_FANTASYPROS_FLEX_AUDIT.md` (the correction) and
`docs/weekly/W2_ECR_BENCHMARK_RESULTS.md` (the benchmark).**

### CURRENT WEEKLY RESEARCH STATUS

- **W1's two data findings are corrected.** A real weekly FLEX board (`position=FLX`, RB/WR/TE,
  zero QBs) and Half-PPR (`scoring=HALF`) both exist historically at FantasyPros for 2021-2025.
  W1 had audited only the DynastyProcess mirror and reported that source's limits as limits of
  the record. **The lesson: an audit that finds an absence must name which SOURCE it is in.**
- **Our FantasyPros key is a public tier**: `limit: 10` rows per board on every endpoint, plus a
  request quota that exhausted after ~120 calls. Access controls — **not circumvented, nothing
  scraped**. Full-depth FLEX and a real Half-PPR benchmark are a **licensing** decision now.
- **The FLEX reconstruction is VALIDATED, not assumed**: median top-10 overlap **0.80** vs the
  real board over 19 weeks (threshold 0.70 fixed before measuring). W1's U3 is resolved.
- **A payload trap was caught**: the API returns players' **current** teams for historical
  weeks, so `player_game_kickoff_ts` would have excluded the wrong players in nearly every week.
  Rule now in code: take only ranking + identity from a ranking source; schedule/roster facts
  come from nflverse.
- **ECR benchmark (79 weeks, 2021-2025, Full PPR)**: FLEX ρ **0.682** (SD 0.041), pairwise
  0.753 — but **precision@10 only 0.260 against capture@10 0.637**. ECR names ~2.6 of the true
  top 10, and those names collect 64% of the achievable points. **K is close to noise**
  (ρ 0.127; the 10th-percentile week is −0.173, worse than random); DST weak (ρ 0.275).
- **Noise floor (FLEX, the number every later phase needs)**: ρ **±0.018**, pairwise ±0.007,
  capture@10 **±0.020**, capture@50 ±0.013. Unit of replication is the **week (n=79)**, paired
  within week. **The draft program's 172-250 floor does NOT transfer.**
- **How strong is ECR really**: it beats a plain season-to-date PPG average by only **+0.066
  Spearman** (3.6 MDE units) and +0.042 capture@10, versus +0.338 over a prior-season baseline.
  That +0.066 is the whole measured value of a 50-expert consensus over arithmetic — and it
  sizes the prize for Alpha. For **K, ECR fails to beat that baseline at all** at depth.
- **Decision rules resolved**: **R1 USABLE** (gap/MDE 2.13-4.00 on FLEX) → W3 may proceed.
  **R2 UNIFORM** everywhere except **K (6.10x, depth-dependent)**.
- **All 11 excluded weeks are missing-ECR weeks**; none is a data-quality exclusion. But they
  are **systematic — week 1 is absent in four of five seasons** — so every number describes ECR
  *conditional on in-season data existing*. Zero invalid cells.
- **Still no Alpha comparison has been run.** The existing weekly model remains W3's starting
  point, not a baseline.
- **Next: W3** — *can Alpha, on Friday-cutoff information and no ECR, beat the season-to-date
  baseline by more than ECR's +0.066 ρ?* Aimed at the top of the board; **not** at K/DST, and
  **not** at projection MAE.

### Earlier status: W1 complete (D109) — **WEEKLY-RANKING PROGRAM OPENED. A valid, leakage-free, reproducible foundation EXISTS for a Friday-cutoff, Full-PPR weekly study over 79 weeks (2021-2025), all six positions plus a reconstructed FLEX. Three things the brief asked for do not exist historically. Nothing shipped.**

Audit and pre-registration only. **No production change: `models/`, `league/`, `api/`, `cli.py`,
configs and `market/consensus.py` untouched; nothing fitted; nothing merged.** This opens a
**second** research program, separate from the draft-choice program D108 closed — it does not
reopen the draft question. **Entry point: `docs/weekly/W1_FOUNDATION_AUDIT.md`. Authority map for
both programs: `docs/README.md`.**

### CURRENT WEEKLY RESEARCH STATUS

- **The foundation is VALID**, scoped to: **one Friday snapshot per week**, **Full PPR**, the
  **79 covered REG weeks of 2021-2025**, QB/RB/WR/TE/K/DST, and a FLEX reconstructed from the
  superflex board.
- **Three brief requirements are absent from the historical record**, not fixable by harness care:
  1. the **Tuesday-Sunday daily cadence** — weekly ECR has **one vintage per week and it is a
     Friday** (82/96 Friday), and the injury file is one *final* row per player-week whose
     `date_modified` is the last edit (4,818 of 2024's on a Friday), so an earlier cutoff deletes
     most of the report rather than rewinding it;
  2. a **Half-PPR ECR benchmark** — no `half`/`standard`/`non-ppr` page exists at any date;
  3. a **1-QB weekly overall/FLEX board** — **D56 repeating itself**; the only weekly
     cross-position board after 2020-10-12 is the **superflex** one.
- **Weekly ECR is NOT ingested.** `DEFAULT_ECR_TYPES` covers only the four draft series; the
  weekly series sit unused in the snapshot this project already downloads.
- **Already-played (Thursday-night) rows must be excluded**: 78 of 90 canonical boards carry them,
  6.0% of rows.
- **Ground truth is verified**: nflverse `fantasy_points_ppr` reproduces an explicit PPR formula
  to **0.0 max abs difference, zero mismatches over 5,864 player-weeks**; half-PPR is an exact
  identity over stored columns.
- **A weekly model already exists and has NEVER been evaluated as a ranking** —
  `models/established/`, 11 features, QB/RB/WR/TE only, no opponent/Vegas/weather/injury/ECR, and
  its evaluation sums weekly predictions into a *season total*. It is W3's starting point, not a
  baseline.
- **Vegas and weather are unusable historically** (untimestamped closing lines; realized game
  conditions). This caps Alpha-without-ECR and is stated before any result.
- **No ranking quality has been measured for any system.** Every comparative claim is still ahead.
- **The draft program's 172-250 detection floor does NOT transfer** — a different instrument.
- **Next: W2**, pre-registered and committed before execution
  (`docs/weekly/W2_PREREGISTRATION.md`): *how strong is the ECR-alone weekly benchmark, and what
  is the noise floor?* One system, no Alpha, no comparison.

### Earlier status: M58 complete (D108) — **PROGRAM CLOSEOUT. The draft-choice investigation D86–D107 is CLOSED and consolidated. Two repository defects D107 missed are fixed. Y1 remains production, unchanged by every phase from D85 to D108.**

Consolidation/audit only. **No production draft logic, no `models/`, no `league/`, nothing fitted,
no new experiment, no new ranking source, no Y1 tuning, no PR, nothing merged, no D109.** `models/`
(`73b408e9`) and `league/` (`d4cfd00e`) byte-identical to `origin/main`. **Entry point for a future
researcher: `docs/D108_PROGRAM_CLOSEOUT.md`.**

### CURRENT DRAFT RESEARCH STATUS

- **Y1 remains production.** It has not been modified by any phase from D85 to D108.
- **Draft-choice research D86–D107 is closed and consolidated.**
- **No alternative decision rule and no tested preseason ranking has demonstrated a measurable
  improvement above the instrument's detection floor of 172–250 points.**
- **This is not a proof of optimality.** The canonical wording, which must be quoted whole:

  > *Within the 2021–2025 evaluation population, the two shipped 1-QB roster configurations, the
  > information sources tested, and the decision rules tested, no alternative decision-rule or
  > preseason-ranking intervention demonstrated a reliably measurable improvement in realized draft
  > value over Y1 above the instrument's detection floor.*

  It does **not** say Y1 is optimal or globally optimal, that the draft is solved, that projections
  do not matter, that no improvement exists, that the decision layer cannot be improved, that ECR is
  useless, or that future projection work is pointless.
- **Travelling caveats:** `ORACLE_Y1` (+795.3 / +717.0) is a **hindsight** information gap, not an
  achievable improvement; the best tested real preseason ranking **did not convert** its
  identification advantage (2.75 vs 1.95 of 6) into draft value (+77.3 / −132.1, both below the
  floor, sign flipping across formats); the decision residual (~86–113 pts/draft) is **below the
  floor**; the ranking ladder shows **thresholded robustness, not optimality**, and is
  **degradation-only with each position's value multiset held fixed**; the plateau is **conditional
  on the tested environment**; and the 92–96% "the oracle's player scored more" share is
  **unattributable** — no part of it may be quoted as projection error.
- **North-star discipline.** (A) MAE/RMSE/Spearman/AUC/top-6 are **projection diagnostics**.
  (B) The product objective is the **realized value of draft choices**, early, middle and late.
  (C) ORACLE_Y1 and pick-level regret are **bounding diagnostics**, not targets. **A projection
  metric earns attention only when it demonstrates downstream draft-value improvement** — D100 →
  D104 is the worked counterexample.

### REOPENING CRITERIA

Reopen the draft-choice question only if at least one occurs: **(1)** substantially more independent
season clusters lowering the detection floor — the only lever (slots cannot, D88; seeds cannot,
D92); **(2)** a **pre-screened** information source materially changing within-position predictive
ordering, against ECR's measured **+0.024** and the ladder's smallest resolvable rung of **−0.035**;
**(3)** a projection change altering value **magnitudes** rather than merely reordering players — an
axis no D99–D106 experiment spans; **(4)** a method identifying the ORACLE_Y1 "scored more" gap in a
**preseason-available** way; **(5)** failure of any instrument-integrity check, or drift of
`models/`/`league/` off the Y1 hashes; **(6)** materially new draft/roster information;
**(7)** transaction/waiver history, which is a **new total-roster-value question**, not a
continuation of this draft-only one.

### What D108 found that D107 missed

**(a) The D93/D94 record is ORPHANED, and it retracts a D86–D92 headline.**
`claude/o1-advantage-attribution-azp7k7` holds 8 commits not in HEAD carrying
`docs/D93_O1_REPLICATION_POWER.md`, a `## D93` entry, a `## D94` entry and an M45 block. Their
*code* reached main (re-landed by D95/D96, verified identical); the writing never did — which is why
`DECISIONS.md` jumps D92 → D95. D93 found tier `O0` reproduced production in **0 of 24 cells**
(D94: 0 of 60) because `_pick_by_tier` omitted `O_TIERS`, so **every O-tier number in D86–D92 was
measured against a control that was never production** and the K/DST mechanism those phases describe
was substantially **an artifact** (ΔnK −0.67 → −0.03 on repair). Forward pointers added at the D86
entry head and the D92 → D95 boundary. Nothing merged.

**(b) A `make lint` regression this stack introduced.** Every phase D98–D107 reported "ruff clean"
having run `ruff check` alone; **`make lint` also runs `ruff format --check src tests`**, which was
never run. `origin/main` passes both halves; HEAD failed with **4 files**, all created or modified
by this stack. Fixed by `ruff format` on exactly those four — **each file's AST is identical before
and after**. No production file, no `scripts/` file. Future phases should run `make lint`.

**D107's own findings re-verified independently:** both corrections confirmed (D103's 0% is
target-only — dynasty is 5.0%/9.0%; D104's histogram is {1:11, 2:5, 3:3, 5:1} target and
{1:11, 2:5, 3:1, 4:2, 5:1} dynasty), and **L0 vs `H` parity 640 agree / 0 mismatches** across both
formats.

**Gates:** 1427 tests pass, 44 deselected; `ruff check src tests` clean; **`ruff format --check src
tests` clean**. Topology: linear, zero merge commits, `origin/main` a strict ancestor 17 behind and
0 ahead; every per-phase branch an exact ancestor of HEAD; **PR #23's head is the stack's first
commit**, so merging the tip subsumes it. **D109 not started.**

### Earlier status: M57 complete (D107) — **The D86–D106 record reproduces from its own artifacts, two statements in it were too strong and are corrected, the instrument passes all fourteen contract checks, and the draft-investigation branch is mature enough to consolidate. A. Nothing ships.**

Audit only. **No production logic, no model, nothing in `league/`, nothing fitted, no new
experiment, no 2026, no new ranking source, no Y1 tuning, no PR, nothing merged**; `models/`
(`73b408e9`) and `league/` (`d4cfd00e`) byte-identical to `origin/main`, and **no source file
changed in this phase at all**. 1427 tests pass, ruff clean. Board vintage re-derived read-only as
`ca3e2d8a…`. Full report: `docs/D107_RESEARCH_CONSOLIDATION_AUDIT.md`.

**Everything re-derivable reproduced exactly** — D100's five methods, D101's four arms on both G6
readings, D103's regret-by-phase and ORACLE_Y1 (+795.3 / +717.0), D104's decomposition
(+77.3 / −132.1), D105's ladder including the seed-SD statistic, D106's weekly ladder and its
self-invalidating regret arm. **All fourteen instrument/data-contract checks pass**, and the one
presentational gap is closed with a measurement: the much-quoted 240/240 L0-vs-production figure was
target-only, and re-running the existing read-only `--mode parity` over **both** formats gives
**640/640 real pick states, 0 disagreements**.

**Two corrections to the record, neither changing a verdict.** (a) D103's *"0% of rounds 1–5 in both
formats"* is false for dynasty (5.0% season-long, 9.0% weekly; target is 0.0%), and the "2.2–4.7%"
range should read **1.9–4.7%**. (b) D104's *"first divergence: round 1, in 20/20 drafts"* overstates:
**all 20 drafts diverge within five rounds; round 1 in 11 of 20.**

**The reframing the record was missing.** Dividing D103's regret by the slate dispersion it already
stores: **0.614 early → 0.739 late (target), 0.606 → 0.925 (dynasty).** In absolute points the
largest losses are early; **as a share of the value actually available at the pick, Y1 does best
early and worst late.** Not a defect — a random pick from the same slate sits at 122.3 against
Alpha's 116.2 (D86) — but the record carried only the absolute reading.

**"Closed" is a stopping rule, not a finding.** The branch stops because experiments of this design
cannot resolve effects of the available size, not because ranking quality is irrelevant: destroying
it costs **566–721 points**. D104 §7's *"the problem is NOT projections"* is too strong. Three limits
belong beside every plateau claim: the ladder is **degradation-only**, holds each position's **value
multiset fixed** (so it says nothing about projection *magnitudes*), and ran against **one** real
alternative source.

**Decision: A — consolidate and close; Y1 remains production.** Not C (no methodological flaw; the
one the program did surface — regret is arm-relative — was declared, observed, and acted on). Not B
(every candidate's plausible effect sits below the 172–250 floor). **Reopening** requires one of:
more season clusters (the only lever that moves the floor — at k=7 it falls toward ~130); a ranking
source moving within-position predictive Spearman by materially more than ECR's **+0.024**,
pre-screened before any draft run; a projection change altering **magnitudes, not order**; a way to
identify the 92–96% "scored more" split; a failure of the fourteen instrument checks; or transaction
history, which opens a different question.

**Repository.** `d106-weekly-sensitivity` at `397e707`; `origin/main` `277204f` a strict ancestor,
16 behind / 0 ahead; **linear, zero merge commits**; the only `src/` file changed across all of
D98–D106 is `evaluation/draft_oracle.py`, imported by no production path. **PR #23 is the only open
PR** and is the stack's first commit, so merging the tip would subsume it.

### Earlier status: M56 complete (D106) — **The D105 plateau is OBJECTIVE-INDEPENDENT. Under the weekly no-foresight objective the intermediate ladder stays inside the noise band in both formats, while the severe end separates MORE. H1. The projection/ranking sensitivity branch stops here. Nothing ships.**

Research only. **No production change, no retraining, no ECR tuning, no new model, no 2026, no PR,
nothing merged**; `models/` (`73b408e9`) and `league/` (`d4cfd00e`) byte-identical; the only
non-doc/test change is one argparse constraint in the research layer. 1427 tests pass, ruff clean.
Full report: `docs/D106_WEEKLY_SENSITIVITY.md`.

**Everything identical to D105 except the realized-value objective.** Two isolation properties
newly pinned by test: the weekly lineup is set from **unperturbed** Y1 projections for every arm
(so the test measures draft quality, not lineup quality), and **pick divergence is
objective-independent** — `_pick_by_tier` takes no objective parameter — so D105's picks-changed
table carries over by construction rather than re-measurement.

| α | target D105 | **target D106** | dynasty D105 | **dynasty D106** |
|---|---|---|---|---|
| 0.50 | −46.5 | **−30.6** | −60.0 | **−84.3** |
| 1.00 | −565.8 | **−621.0** | −631.9 | **−721.3** |
| FP_ECR_Y1 | +77.3 | **+48.4** | −132.1 | **−202.4** |

At α=0.50 the delta is below its seed SD **and** below the 172–250 floor in both formats under both
objectives. **Both H0 criteria fail → H1.**

**My stated prior was half wrong.** I predicted weekly would compress the whole ladder; it
compresses the *intermediate* region at target (plateau ratio 8.2% → 4.9%) but **amplifies the
endpoint** (+9.8% target, +14.1% dynasty). **Weekly makes the threshold sharper, not shallower.**

**ECR gets worse under the more faithful objective** — target +77.3 → +48.4 (0/5 → 2/5 seasons
worse), dynasty −132.1 → **−202.4**, now worse in 5/5. D104's negative result strengthens.

**The matched regret ladder invalidates itself, and vindicates the primary choice.** Weekly regret
is non-monotone (L0 96.8, L2 **73.2**, L4 154.5) and *contradicts* the value curve at α=0.50, where
regret falls while realized value also falls. That is the arm-relative artifact declared in the
pre-registration, now observed: a scrambled board scrambles the **oracle's** rollouts too, and the
engine matches the oracle *more* often on a degraded board (4.4% → **8.1%**). Had regret been the
primary outcome, D106 would have reported that moderate scrambling improves drafting. **No
phase-level claim is made.**

**This closes the projection/ranking direction** as the explanation for the missing improvement, and
the sensitivity branch stops per the pre-registered rule. It does **not** mean the objective is
defective: the evidence supports a **thresholded decision environment** where only improvements
large enough to move predictive Spearman by ~±0.5 can register. ECR moves it by 0.024.

**Cumulative position (D97–D106):** decision residual ~86–113 pts (below floor); perfect information
worth ~+670–795 but the best available ranking recovers ≤10% and is negative in dynasty; the value
surface is a plateau under **both** objectives; the decision surface is steep. **Y1 operates where
neither better rankings nor a better rule produces a measurable gain** — a conclusion about the
problem, now supported rather than assumed.

### Earlier status: M55 complete (D105) — **The objective is NOT flat, it is THRESHOLDED. 88% of picks can change for 46 points, but a full scramble costs 566. The decision surface is steep; the value surface is a plateau, and every ranking source tested lives inside it. B — ROBUST. Nothing ships.**

Research only. **No production change, no retraining, no ECR tuning, no 2026, no PR, nothing
merged**; `models/` (`73b408e9`) and `league/` (`d4cfd00e`) byte-identical and **no `src/` file
changed at all**. Full report: `docs/D105_OBJECTIVE_SENSITIVITY.md`.

**The ladder.** Within position, players re-ordered by `(1−α)·rank_Y1 + α·rank_random`, with Y1's
**own values** re-assigned down that order — the same machinery as D104's ECR substitution, so the
two sit on one comparison. α=0 reproduces Y1 exactly (0.0% pick divergence end-to-end); α=1 is a
uniform permutation. It degrades **predictive** quality, not just agreement with Y1: Spearman vs
realized 0.753 → 0.718 → 0.527 → 0.242 → **0.003**.

**The curve is thresholded:**

| α | Spearman vs realized | **picks changed** | **value vs Y1** (target) |
|---|---|---|---|
| 0.25 | 0.718 | **66.2%** | −41.1 |
| 0.50 | 0.527 | **88.4%** | **−46.5** |
| 0.75 | 0.242 | 90.6% | −115.0 |
| 1.00 | 0.003 | 98.4% | **−565.8**, 5/5 seasons, CI [−829, −303] |

Dynasty matches: −39.5 / −60.0 / −217.7 / **−631.9**.

**The decisive result is the decoupling.** At α=0.50 the engine takes a different player at seven
of every eight picks, from pick 1, and value moves **46.5 points** — below the floor and smaller
than the seed-to-seed SD of that level (160). **The decision surface is steep; the value surface is
flat.** A decision rule cannot extract value from ordering differences the outcome does not reward.

**Pick-level regret corroborates, with the same threshold shape** (target, L0/L2/L4): all-picks
regret **126.2 → 137.3 → 228.4** — L0→L2 costs +11.1, L2→L4 a further +91.1. The feared artifact
(a scrambled board also weakening the oracle, pushing regret *down*) **did not appear**.

**D104's null is explained, and my D104 "flat objective" hypothesis is RETRACTED.** Scrambling
destroys 566–632 points — larger than anything measured on the decision side — so the objective is
not flat. The correct statement is narrower: **it has a broad robustness plateau, and every ranking
source tested lives inside it.** ECR improves predictive Spearman by **+0.024**, one-tenth of the
smallest rung; its value effect is the size of the noise.

This reframes ten value bases, a weekly objective, legality separation, per-position calibration,
identification work and a real market ranking as failing for **one structural reason** rather than
as six separate disappointments.

**What it would take:** a ranking change must move predictive Spearman by roughly **±0.5** to reach
the 86–113 pt scale of D103's decision residual. Stated as the extrapolation it is — the ladder
measures degradation, and symmetry is not established.

**Next:** re-run this exact ladder under the **weekly no-foresight** objective. If the plateau
persists it is a property of the draft and ranking-side work closes on positive evidence; if the
weekly objective resolves L1/L2, the **objective** is what to fix, not the projections.

### Earlier status: M54 complete (D104) — **The best real preseason ranking recovers only +9.7% of the oracle gap in target and is NEGATIVE (−18.4%) in dynasty, while changing 57–64% of all picks. The draft objective looks FLAT near Y1. B — SMALL / UNCERTAIN. Nothing ships.**

*[D108 marker: the "looks FLAT" hypothesis in this heading was **retracted by its own author in
D105 §6** — the objective is **thresholded**, not flat (a full within-position scramble costs
566–632 points season-long, 621–721 weekly). The "first divergence round 1 in 20/20 drafts" figure
in this block is corrected in D107 §2 C2: all 20 diverge within five rounds, round 1 in 11 of 20.
The +9.7% / −18.4% recovered fractions reproduce exactly.]*

Research only. **No production change, no model fitted, no ECR tuning, no 2026, no PR, nothing
merged**; `models/` (`73b408e9`) and `league/` (`d4cfd00e`) byte-identical and **no `src/` file
changed at all**. Full report: `docs/D104_ECR_FLOOR.md`.

**Phase 0 rejected the repository's own ECR→value transform before any result.**
`ecr_implied_baseline` (a) collapses the top of the board — the 2023 top-24 holds **4 distinct
values at RB, largest tie group 12** — so the engine would pick **alphabetically** exactly where
regret is concentrated; (b) **hardcodes `ecr_type='ro'`**, so dynasty would be fed the redraft board
(D56 violation); (c) covers only 66–75% of the board. Used instead: a **within-position permutation
of Y1's own values** into preseason ECR order, which preserves the value multiset exactly (asserted
at runtime, pinned by test), keeps the universe identical, and introduces no ties.

**ORACLE_Y1 reproduces D103 exactly** (+795.3 / +717.0), so the instrument is sound.

**The decomposition** (realized roster value, Y1 rule held fixed, 20 drafts per arm per format):

| contrast | target_league | dynasty_1qb |
|---|---|---|
| **Y1 → FP_ECR_Y1** | **+77.3**, 5W/0T/0L, CI [−44.1, +198.6] | **−132.1**, 1W/0T/4L, CI [−371.1, +107.0] |
| FP_ECR_Y1 → ORACLE_Y1 | +718.0 | +849.1 |
| Y1 → ORACLE_Y1 | +795.3 | +717.0 |
| **recovered fraction** | **+9.7%** | **−18.4%** |

Both below D97's 172–250 floor → **UNRESOLVED by the pre-registered stopping rule**, the positive
one included. The **sign flips across formats**, so no mechanism is demonstrated.

**The key number: 57–64% of picks change, from round 1 in every draft, and value barely moves.**
The draft outcome is remarkably **insensitive to within-position board ordering** — exactly what
D103's "92–96% luck-shaped" predicts.

**Pick-level regret corroborates it.** Target format, 320 audited picks per arm: Y1 **134.8**,
FP_ECR_Y1 **139.8** — **+5.0, slightly worse**, CI [−33.2, +43.3], better in 2/5 seasons. Damage is
concentrated LATE (107.4 → **122.8**) and at TE/K/DST, the cross-position confound of holding K/DST
fixed while re-assigning skill values.

**The distinction the phase existed to test:** *"FantasyPros identifies better players"* (D100:
2.75 vs 1.95 of 6) **does not imply** *"FantasyPros produces better draft picks."* This is the
clearest demonstration the project has that **projection proxy metrics do not transfer to pick
quality**, and it retires the reasoning chain running from D97 through D100.

**Direction challenged:** the evidence now says the problem is **NOT projections** in the sense the
last six phases assumed. D103 put the decision residual at ~86–113 pts/draft; D104 puts the best
available preseason-information gain at +77.3/−132.1. **Neither lever shows reachable headroom above
the measurement floor.** The new hypothesis: **the draft objective is FLAT near Y1's operating
point**, which would explain why ten value bases, a weekly objective and legality separation all
failed — a property of the problem, not a failure of the search. *[D108 marker: this hypothesis was
tested in D105 and **REJECTED** — the objective is **thresholded**, a broad robustness plateau with
a steep collapse beyond it. The explanatory role survives; the word "flat" does not.]*

**Next:** test the flatness directly — dispersion of realized value across deliberately scrambled
within-position boards at increasing intensity, rule held fixed. If scrambled boards land in the
same ±130-point band ECR does, the projection direction closes on **positive** evidence rather than
repeated nulls.

### Earlier status: M53 complete (D103) — **Pick-level regret is concentrated EARLY (181.5 vs 107.4), the weekly objective REDUCES regret everywhere rather than exposing late-round value, and perfect information is worth +795.3 with the rule held at Y1. D — NOT CONFIRMED. Nothing ships.**

Research + instrumentation. **No production decision-rule change, no model fitted, no 2026, no
PR, nothing merged**; `models/` (`73b408e9`) and `league/` (`d4cfd00e`) byte-identical; 1392 tests
pass (1370 baseline + 22 new), ruff clean. The only `src/` change is `evaluation/draft_oracle.py`,
an instrument. Full report: `docs/D103_PICK_LEVEL_OBJECTIVE.md`.

**Production equivalence is now pinned.** `draft_oracle.py` claimed L0/Q0/Z0 were asserted
byte-identical to `recommend_draft_pick` by existing tests; **no such test existed**.
`TestShippedTierIsProduction` now walks whole drafts at every slot comparing the chosen player
against tier `H` at every audited state.

**The objective is selectable and D86 still reproduces.** `SEASON_LONG` stays the default (pinned
by test); `WEEKLY_NO_FORESIGHT` reuses the tested weekly objective and refuses to run without its
data. Two rosters differing only in a bench QB score identically under season-long and differ under
weekly.

**Regret by phase — EARLY in every cell** (320 audited picks per format per objective,
2021–2025 × slots {1,4,7,10} × both formats):

| format / objective | all | EARLY 1–5 | MIDDLE 6–10 | LATE 11–16 |
|---|---|---|---|---|
| target / season_long | 134.8 | **181.5** | 121.0 | 107.4 |
| target / weekly | 107.4 | **162.5** | 89.1 | 76.7 |
| dynasty / season_long | 141.8 | **181.1** | 144.2 | 107.0 |
| dynasty / weekly | 103.1 | **147.6** | 98.1 | 70.2 |

Worst round is **round 2** (198.3); Alpha matches the oracle in 0% of rounds 1–5. *[D107 §2 C1,
re-verified in D108: that 0% is `target_league` only — `dynasty_1qb` is 5.0% season-long and 9.0%
weekly. The regret figures above reproduce exactly.]*

**TWO D102 CLAIMS ARE REFUTED.** (a) "Season-long makes late regret near-degenerate by
construction" is **wrong** — late regret is 107.4, and the allocator picks the best ten of sixteen
*by season total*, so a good late pick does enter the lineup; what season-long cannot see is
**insurance** value. (b) The weekly objective **reduces** regret everywhere (−27.4 target, −38.7
dynasty; late −30.6, −36.8) because a weekly lineup adapts and so **compresses** the candidate
spread. **The experiment D102 recommended was run and its motivating hypothesis did not survive.**

**Attribution:** 92–96% of divergences are the oracle's player simply scoring more (his median rank
on Alpha's own board is 73 of ~610); the structural residual is 4.5–7.9%, worth **~91 pts/draft** —
**an independent replication of D86's ~90 on a different slot set** — against D97's ~172–250
measurement floor. 75% of divergences are cross-position.

**ORACLE_Y1 corrects D102 again.** Information effect with the rule held at Y1: **+795.3** (target,
CI [+579.1, +1011.4], 5/5) and **+717.0** (dynasty, 5/5). The implied decision-rule effect under
oracle information is ~−11/−12 points — **D102 predicted Y1's hedging would be actively harmful
under certainty; it is not**, so D97's reading was close to right. (Cross-run slot sets, so the ~11
is indicative.)

**Diagnosis:** predominantly **A** (bad information / unavoidable variance), small persistent **B**
below the detection floor. The honest limit: "scored more" conflates bad information with
unavoidable variance and this instrument cannot separate them, so no share of the 92–96% may be
quoted as projection error.

**Next (documented only, not started):** ORACLE_Y1 is an upper bound on nothing achievable.
Substituting the best **preseason-available** ranking already in the repo (the FantasyPros
consensus board) with the rule held at Y1 would put a **floor** under the same contrast; the gap
between that floor and +795.3 is the only honest estimate of what better projections could buy.

### Earlier status: M52 complete (D102) — **The pick-level objective is already instrumented (D86's `draft_oracle.py`) and has been measured with the roster-value function D86 itself disproved. The project has never validly measured late-pick quality. Definition phase; nothing ships.**

Definition / research only. **No production change, no model fitted, no arm created or modified, no
draft simulation, no 2026, no PR**; `models/` (`73b408e9`) and `league/` (`d4cfd00e`) untouched;
1370 tests pass, ruff clean. Full report: `docs/D102_PICK_LEVEL_OBJECTIVE.md`.

**The metric the north-star needs already exists.** `evaluation/draft_oracle.py` measures
`regret(p) = max_c V(c) − V(chosen)` where `V(c)` is the final roster's realized value after taking
`c` and playing on with the shipped engine. Its information boundary is correct and structurally
pinned (outcomes score a finished roster and nothing else). The engine likewise already prices picks
*marginally* — `marginal_starter_value`, `daVORP`, `positional_opportunity_cost` — so §6/§7 of the
brief describe the existing design, not a gap.

**The defect is the roster-value function.** `_score_roster` uses season totals and one lineup
allocation — the objective D86's own Phase 1 proved **prices the bench at exactly zero**, while
measuring **17.8% of realized points** coming from players it never starts. **Rounds 13–16 are bench
picks, so late-pick regret is near-degenerate by construction: the project has never validly
measured the segment the objective explicitly names.** `weekly_objective.weekly_lineup_points_no_foresight`
already exists and is a one-call-site substitution.

**Validation run (240/240).** `draft_oracle.py` claims L0/Q0/Z0 are pinned to `recommend_draft_pick`
by tests; **no such test exists** (L0 is compared only to its sibling replicas). Checked
empirically: **L0 and H agree on 240 of 240 real pick states**, so the D86 lineage is sound — the
property holds, only the guarantee is missing.

**The oracle gap is not identified.** D97's `ORACLE − PROD = +784.6` confounds information with
decision rule; the missing 2×2 cell is **`ORACLE_Y1`** (perfect projections, production rule). Note
`survival`/`confidence`/`opportunity_cost` are uncertainty machinery with nothing to hedge under
certainty, so a large negative interaction is plausible.

**Challenge to D97–D101: the diagnosis stands, the prescription does not.** "The decision layer is
not binding" is independently corroborated by D86 (~90 pts/draft structural vs ~128 MDE) and is
**not overturned**. But "resolvable" was conflated with "achievable", and **D98–D101 never measured
a draft pick** — four phases on MAE/Spearman/AUC/top-6, none shown monotone in pick quality, and
D101 proved they are not monotone in each other. D86 had explicitly listed projection work under
"Not recommended next".

**Hierarchy:** (1) pick quality via `regret_weekly`, reported **by draft phase** and decomposed into
luck / decision / information / uncertainty; (2) resulting roster, weekly no-foresight, as
validation only; (3) projections — **demoted and conditional** on moving the pick metric;
(4) MAE/RMSE/Spearman/AUC/top-6 — **diagnostic only**.

**Next (D103), all diagnostic:** pin `L0 == H`; re-score the existing 320 oracle pick states with
the weekly no-foresight objective and report regret by draft phase; add the `ORACLE_Y1` cell.

### Earlier status: M51 complete (D101) — **D78's recorded "Y3 passes all seven gates" does not reproduce: Y3 FAILS G6 at WR, and is also worse than Y1 at top-6 identification. DO NOT SHIP. The training-set axis is closed.**

Research only. **No production change, no retraining, no draft run, no PR**; `models/`
(`73b408e9`) and `league/` (`d4cfd00e`) untouched; 1370 tests pass, ruff clean. Full report:
`docs/D101_Y0_Y3_IDENTIFICATION.md`.

D100's recommended experiment was run with the arms unmodified — training frames from the shipped
`select_training_rows`, fits from the shipped `_fit_predict`, and a parity check that re-derives
`measure_arm`'s own metrics from the retained predictions and aborts on any disagreement.

**The decisive finding arrived before identification did.** On the current snapshot **Y1 passes all
seven gates, Y2 fails G6 at RB, and Y3 FAILS G6 at WR** — where D78 recorded Y3 as passing. Code
drift is ruled out (D79's only edit is a default-preserving refactor, verified by diff);
nondeterminism is ruled out (three repeat fits identical to nine decimals); data/library drift is
the remaining explanation and the pre-D78 database is unrecoverable (D91). **Any future citation of
"Y3 passes all seven gates" must be re-derived, not quoted.**

**G6's prose and its code are different statistics** — "mean |top-decile signed bias|" versus the
`|mean|` the code computes. Y2's failure set changes between readings ([RB] vs [RB, WR] — D78's own
narrative matches the prose, not the code); **Y3 fails at WR under both**, so the ambiguity does not
change the answer. Gates were evaluated as coded and unchanged.

**Identification: Y1 wins.** top6_hit_rate Y0 0.3438, **Y1 0.3750**, Y2 0.3229, Y3 0.3646.
**Y3 − Y1 = −0.0104** (5W/6T/5L cells, 1W/1T/2L seasons); no position consistently favours Y3.
AUC and Spearman rank Y3 first while hit rate ranks Y1 first — D100's point on new data, and the
reason **G4's Spearman gate cannot be treated as a proxy for identification.** Every interval spans
zero; declared exploratory in advance.

**Population.** The registered window is 2022–2025, not 2021–2025: ECR coverage is 0.000 for
2016–2019, so at target 2021 both Y2 and Y3 fall back to their controls **exactly** (verified
byte-identical). Y2 also falls back in all four 2022 cells, so it is treated in only 3 of its 4
registered seasons.

**A harness defect was found and fixed**: season win/loss counting used a bare `> 0`, and 2024's
cancelling cells average to 6.94e-18, which was counted as a win. Fixed with an explicit tolerance
and a regression test carrying the real counts; all numbers are post-fix.

**Verdict: DO NOT SHIP.** The D78 selection rule re-applied re-selects **Y1 — already in
production**. Y1 = class B, Y2 = class D, Y3 = class C, and Y3 satisfies **neither** condition
required to prefer it over Y1. No arm is justified for downstream draft testing.

**Next — settle the criterion, do not invent Y4.** D79, D100 and D101 have now hit the same wall
from three directions: the gates measure pool-wide accuracy over ~150 players while the product
consumes the top ~20. Smallest next experiment, on measurement frames that already exist: pre-register
whether the projection criterion is pool-wide accuracy or top-of-board identification, and which of
G6's two readings is binding. That unblocks D79's E2 arm without fitting anything new.

### Earlier status: M50 complete (D100) — **M6 is beaten at top-6 identification by one of its own raw input features. Some of the signal is already in the feature set and discarded (13% of the gap); most of it is genuinely absent (45%). PROMISING BUT UNRESOLVED. Nothing shipped.**

Diagnostic only. **No production change, no retraining, no draft run, no PR**; `models/`
(`73b408e9`) and `league/` (`d4cfd00e`) untouched; 1360 tests pass, ruff clean. Full report:
`docs/D100_FEATURE_SIGNAL_DIAGNOSTIC.md`.

**The headline.** On M6's own prediction set over 2021–2025 × QB/RB/WR/TE, `preseason_ecr_rank`
used **raw, with no model at all** finds **2.75 of 6** realized top-6 players against M6's
**1.95** — and also beats M6 on AUC (0.925 vs 0.899) and Spearman (0.790 vs 0.767). Paired over
seasons: **4 wins, 1 tie, 0 losses**; 11W/8T/1L across the 20 position-seasons. The shipped
`ecr_implied` isotonic map reproduces the same +3.20.

**The negative control is null**, which is what makes this more than noise: `D_gbm` — M6's own
CatBoost, M6's own features, only the training split changed, including a non-causal split allowed
to see the future — gains +0.50 to +1.60 with CIs spanning zero. Features and data quantity are
constant; the target and loss are what change. M6's output tracks `prior_weighted_total` at ρ
0.94–0.97 and ECR at 0.92–0.94: a blend of two correlated, differently-wrong rankings, and blending
shrinks toward the middle exactly where the top-6 lives.

**Four features, about two dimensions.** corr(`prior_ppg` × `prior_games`, `prior_weighted_total`)
= **0.972**. Three of the four are encodings of last year's production; ECR is the only independent
dimension. **`prior_games` is anti-signal** (0.90 of 6; **0.00 at RB in every season**) and dilutes
every aggregation it enters — **D69's availability/durability thread is closed.**

**Where the signal is not.** WR **+1.60** and RB **+0.80** (neither ever negative); TE +0.60, weak;
**QB +0.20 — absent**; **K undefined, because M6 has no kicker model at all**. That is the opposite
of where D97 said the value was.

**Ceiling — both H3 and H4 are partly true, H3 larger.** Of the 6.00 gap: 1.95 found by M6, **+0.80
extractable but discarded (13%)**, +2.70 not in these features even under LOSO (45%), +0.55
structurally unreachable (rookies / no prior season, 9%).

**Why not SHIP.** Fourteen methods were compared; **none survives multiplicity correction** at five
clusters. 2023 is null everywhere, QB is null throughout, and the hypothesis cannot be tested
without building a new projection — which this phase forbids. No draft run, no 2026 check.

**Next — the repository already names it.** D78's **Y3** (= Y1 + the Y2 ECR-sentinel repair) passed
all seven gates and was deliberately deferred under the lowest-numbered-arm rule. **Every one of
those seven gates is MAE / RMSE / Spearman / top-decile bias; not one is an identification gate**,
though `evaluation_results` already carries `top12_hit_rate`. Smallest next experiment: **re-run
D78's existing Y0–Y3 arms unchanged with a pre-registered top-6 identification metric added, stating
in advance whether identification may override an MAE gate.**

### Earlier status: M49 complete (D99) — **Per-position calibration CANNOT improve top-6 identification, for a structural reason: these calibrations are monotone within a position and identification depends on within-position order. REJECT. Nothing shipped.**

Research only. **No production change**; `models/` (`73b408e9`) and `league/` (`d4cfd00e`)
untouched; 1350 tests pass, ruff clean. Full report: `docs/D99_PROJECTION_CALIBRATION.md`.

**The experiment already existed.** `evaluation/projection_calibration.py` was committed in D68
before any arm was fitted and pre-registers exactly the forms D99 proposed (X0 control, X1
additive, X2 affine, X3 rank-band, X4 empirical-Bayes). D68's outcome: every arm improved MAE
(63.29 → 61.83–62.88) and every arm failed its gates. **K and DST are excluded from all arms**
(D57), so D97's "start with QB/TE/K" is only answerable for QB and TE.

**The primary result is structural.** X1/X2/X4 are monotone increasing within a position, so they
cannot reorder it, and top-6-by-position is a pure function of that order. Stated as H0 before
running and confirmed exactly: cells where per-position top-6 differs from control, of 30 —
**X1 0/30, X2 0/30, X4 0/30, X3 1/30**. D97's identification failure is a within-position *ranking*
failure; these calibrations rescale without reordering. **D97's recommendation #1 is closed as
specified — it targets the wrong mechanism.**

**What calibration can move:** cross-position allocation. First-QB overall rank on treated seasons:
control 5.0, X1/X4 5.0 (**inert by construction** — a uniform additive shift leaves
`draft_aware_vorp` invariant), X2 **10.3**, X3 **11.0**, oracle 10.0. A real signal in D97's
predicted direction — but not the primary metric, and both arms were already rejected by D68.

**Power closes the thread:** only 3 of 5 seasons are treatable (2021/2022 are control by
construction), giving MDE **~345–360 points** — larger than Y1's entire decision apparatus
(+213.8). Phases 7–8 were not run, per the pre-registered stopping rule.

**Next:** the identification failure is a ranking problem, so a fix needs new *information*, not a
rescaling. Smallest next question — do M6's existing four features already separate the realized
top-6 from the projected top-6 out-of-sample? That distinguishes "the model discards signal it has"
from "the information is not in the data".

### Earlier status: M48 complete (D98) — **The D56 concern in the projection feature path is a FALSE ALARM. The ECR feature is already semantically correct, the obvious "fix" would be a regression, and calibration is unblocked. Nothing shipped.**

Input-integrity check before calibration. **No production change, no model change, no retraining.**
`models/` (`73b408e9`) and `league/` (`d4cfd00e`) untouched; 1350 tests pass, ruff clean.

`models/established/season_level.py`'s ECR subquery **is** the production projection feature path —
M6 imports `load_season_level_data` and `FEATURES` from it directly — and training and inference
carry the identical query, so there is no train/serve skew.

**The concern does not fire.** Of the ECR rows that actually reach the model, **0.0% come from the
IDP page in every season 2021–2025** (398/398, 406/406, 395/395, 431/431, 386/386 from
`redraft-overall`). IDP-page players are defensive, have no QB/RB/WR/TE row in
`player_season_stats`, and are dropped by the join. Across 2021–2026 exactly **two** players ever
hold same-date rows on both pages: one never reaches the model, and the other's ties (July 2026)
are always superseded by a later August `redraft-overall` scrape.

**Decisive test:** the semantically-correct feature — the page carrying *this* season's PPR board,
resolved via `preseason_page_type` — is compared row by row against production's. **Zero differing
values in every season 2020–2026, including live 2026.** Identical inputs, so prediction delta,
MAE delta and top-6 overlap delta are all analytically **exactly zero**.

**The naive fix would be a regression.** A `page_type = 'redraft-overall'` filter destroys 2020's
feature (**366 ECR values → 0**), replacing them with the 999 "no market opinion" sentinel: 2020's
board is published under the pre-rename label `redraft-offense`, the *same* FantasyPros page (D95).

**Recorded, not fixed:** two latent fragilities — no `page_type` filter (correctness is contingent
on IDP players lacking offensive stat lines) and no deterministic tie-break on `scrape_date`. Both
are currently inert, both would be fixed by scoping to `preseason_page_type`, and that change is
**provably a no-op on six seasons of real data** — so it belongs with the next change that touches
this file, not as a standalone edit to `models/`.

**Next:** D97's ranking stands minus its item 2 — per-position calibration of M6 starting with
QB/TE/K, optimising top-6 *identification* rather than MAE. Full record: `docs/DECISIONS.md` D98.

### Earlier status: M47 complete (D97) — **The decision-layer investigation is CLOSED. The value Alpha leaves on the table is projection error, not decision error, and no decision-layer candidate is even detectable on this instrument. Y1 remains production; nothing shipped.**

Diagnostic only — no production change, and **no candidate was run**, because the phase's own
criteria rejected every hypothesis before one was tested. Instrument: D95/D96 contract, vintage
`ca3e2d8a…`, 2021-2025 × 10 slots, both 1-QB formats, production reached through tier `H`.

**The decomposition.** Three arms, identical drafts, differing only in the ranking key: `NAIVE`
(classic VBD on projections), `PROD` (shipped Y1), `ORACLE` (realized points, *same rule as
NAIVE*). So `NAIVE→PROD` isolates the decision rule and `NAIVE→ORACLE` isolates the projections:

| contrast | target_league | dynasty_1qb |
|---|---|---|
| `PROD − NAIVE` (all of Y1's machinery) | **+213.8** [+34.4, +393.2] | **+35.7** [−174.3, +245.8] |
| `ORACLE − NAIVE` (perfect projections) | **+998.4** [+742.5, +1254.3] | **+740.4** [+530.6, +950.1] |
| `ORACLE − PROD` (headroom left) | **+784.6** [+612.7, +956.4] | **+704.6** [+455.0, +954.3] |

Perfect projections are worth **~4.7×** everything the decision layer has ever been worth, and the
decision layer is worth statistically nothing in dynasty.

**Why.** Production takes its first QB in round **2.1**; perfect foresight waits until **7.1**.
That is explained entirely by measured per-position projection bias — top-6 projected QBs are
projected at +61.6 VORP and realize **−3.6** (biased high in 5 of 5 seasons); TE +38.2 → +3.0;
K +18.4 → −5.8; RB is the least biased (+85.1 → +72.0). The bias ranking predicts `ORACLE`'s
reallocation (RB +1.02, K −0.64) exactly. And the value is *present* — the actual top-6 QBs
returned +69.7 — the projections just cannot identify them: **top-6 overlap is 23-40% at every
position**, and QB/TE/K capture ~0% of the available surplus.

**Components** (restated, 2021-2025, parity-verified): `daVORP` owns the endgame (138/160 late),
`msv` the opening (73/160 early), `capacity` binds only late as a constraint, `opportunity_cost`
moves 9%/5% of picks — and is **calibrated, not broken** (corr 0.88 QB / 0.76 WR / 0.73 RB against
the drop that actually occurred; it understates magnitude 20-65%). Left alone.

**Power is the decisive fact.** MDE is **172-250 points** and cannot be lowered: 5 season clusters
and 10 slots are both hard caps, and seeds contribute zero. Y1's whole apparatus is worth +213.8 —
barely above its own MDE. Any incremental decision-layer refinement would need to be worth roughly
as much as all of Y1 just to be *detectable*. Projection headroom is 3-4× the MDE.

**Next direction — projections:** (1) per-position calibration of M6, starting with QB/TE/K;
(2) the D56 defect still live in the feature path (D96 §7) — `models/established/season_level.py`
builds `preseason_ecr_rank` with **no `page_type` filter**, feeding M6's most valuable feature a
merged PPR+IDP rank space; (3) optimise top-6 *identification*, not MAE.

`models/` (`73b408e9`) and `league/` (`d4cfd00e`) unchanged. Full record: `docs/DECISIONS.md` D97.

### Earlier status: M46 complete (D96) — **The benchmark window now agrees with the board contract (2021–2025), the last bypass that could reach 2020 is closed, and D93 is restated on the covered window. The restatement does not change D93's verdict: O1 stays REJECTED, Y1 remains production.**

Instrument hygiene only — no objective research and **no new grid was run**. The restatement is a
re-aggregation of cells D93 already measured (`git_head f11c899`, vintage `74b2ea7d…`).

**The valid historical evaluation population is 2021–2025.** `BACKTEST_SEASONS` is narrowed from
six seasons to five, and a test now asserts the window as a *property* over `ALL_SERIES`
(`series.covers(season)`) rather than as a literal, so a later-starting series fails loudly instead
of silently widening the benchmark. This deliberately changes `compute_board_vintage`'s combined
hash — the population a vintage covers is part of the board identity it names.

**The bypass D95 could not close is now closed.** D95 correctly left an *explicitly named*
page_type alone, but `scripts/d92_paired_grid.py` names one on every run via `preseason_page_type`,
which resolves 2020 to the pre-rename label. That is exactly how every 2020 cell in D89–D93 came to
exist. The runner now refuses an uncovered season before any draft runs.

**D93 restated** (OLD 6-season, contaminated → **CORRECTED 2021–2025, authoritative**):
`target_league` **+3.8 → +7.0**, CI [−54.1, +68.2], MDE 47.0 → **61.2**; `dynasty_1qb`
**+27.1 → +30.7**, CI [−13.9, +75.2], MDE 34.9 → **44.6**. Both CIs still span zero; the claimed
K/DST mechanism stays ≈0 in both formats; dynasty's +30.7 now sits *below its own MDE*, i.e.
formally unresolvable. **Dropping the contaminated cluster cost power rather than buying
confidence** — the corrected instrument resolves *less* than the contaminated one appeared to.
Nothing here strengthens the case for O1.

**Production parity re-verified through the real engine:** `target_league` O0 is **50/50 identical
to tier `H`** (`recommend_draft_pick` itself, not `score_candidate`), as are L0/Q0/Z0.

**D93's O-tier dispatch repair is merged here.** Left separate through D94/D95, but D96's trust
check forced it: on `main` the draft-aware chain still omitted `O_TIERS`, so any experiment run
from `main` would silently revert its control to the D65-era static replacement level. 12 lines in
`evaluation/`, no production path, with the guard that asserts every tier in
`DRAFT_AWARE_REPLACEMENT_TIERS` gets a draft-aware level through `_pick_by_tier`.

**Open, recorded not fixed:** `models/established/season_level.py` builds M6's `preseason_ecr_rank`
with no `page_type` filter, merging the PPR and IDP boards — the D56 problem, still live in the
*feature* path. Out of scope here (`models/` is untouched by mandate).

`models/` (`73b408e9`) and `league/` (`d4cfd00e`) unchanged. Full record: `docs/DECISIONS.md` D96.

### Earlier status: M45 complete (D95) — **A season before 2021 has no preseason market board under any shipped series, and an empty board was not inert: production silently fell through to drafting by alphabetical player_id. `_preseason_overall_market` now refuses it by name.**

Root cause: every shipped series' `page_type` label was introduced by the upstream DynastyProcess
mirror on **2020-10-16** (verified from the raw parquet's `fp_page` column, which the ingested
`market_snapshot` table does not carry) — the same FantasyPros pages exist earlier under different
labels (`ro/redraft-offense` carries `fp_page='ppr-cheatsheets'`, the same page `ro/redraft-overall`
carries from 2021), so no shipped series (`ro`, `rsf`, `do`, `dsf`) has a **preseason** (Jul/Aug)
board before 2021. `_preseason_overall_market` returned `{}` for such a season rather than raising,
and empty is not inert: `opportunity_cost.py::best_by_market_rank` scores every player
`float("inf")` and falls through to its `player_id` tie-break, so "best available by consensus"
silently becomes "first alphabetically" — propagating into the opponent replay, the D67 demand
target and the draft-aware replacement level, with every number staying finite. D89 had already
drawn exactly this line for the simulated opponent (`EmptyMarketBoardError`, after finding the `dsf`
series had no 2020 board) but never generalized it to `ro` or enforced it at the query itself.

`MarketSeries` now carries `first_preseason_season` (2021, measured per series) and
`_preseason_overall_market` raises `MissingMarketBoardError` naming season, ecr_type, page_type,
series label and reason — scoped only to a page_type *resolved from the series*, so a caller naming
one explicitly (`preseason_page_type`'s pre-rename-label lookup) is left alone. The pre-rename 2020
rows are **deliberately not substituted**: a different `(ecr_type, page_type)` pair is a different
series by D56's definition, and adopting one would silently change what every historical number
means — that is a series-definition decision needing its own pre-registration.

**Production impact: none for any valid input.** 64 `recommend_draft_pick` calls across 2024 and
live 2026 (all 16 rounds, two draft slots) produce byte-identical output — matching sha256, every
candidate score to 9 decimals — against this same commit without the fix. 2019/2020 requests now
fail loudly instead of silently. `models/` (`73b408e9`) and `league/` (`d4cfd00e`) unchanged.
**1345 tests pass** (1338 before), ruff clean. Full report: `docs/DECISIONS.md` D95.

### Earlier status: M44 complete (D92) — **The historical ECR board is IMMUTABLE; D91's vintage finding is RETRACTED. The real irreproducibility is that D88–D90's runner was never committed. The instrument is now versioned. Nothing shipped.**

An instrumentation/reproducibility phase. Full report: `docs/D92_BOARD_VINTAGE_INSTRUMENT.md`.
`models/` (`73b408e9`) and `league/` (`d4cfd00e`) unchanged from the Y1 baseline; the only `src/`
change is two additive research files no production path imports. **1338 tests pass** (1318 before).

**D91's central claim was my measurement error, and it is retracted.** D89's published column counts
market-ranked players *inside the projected board*; D91 counted every `market_rank` entry, a
superset. Measured consistently, **~90 published D89 input figures reproduce exactly** — board
composition, consumption demand, best K/DST ranks, uncertainty counts, ECR dispersion, coverage to
the decimal.

**The board is provably immutable for history.** `db_fpecr.parquet` is committed weekly to a public
repo; the blob at commit `9338630` (2026-09-11 04:31Z) hashes to `a966176d…` — byte-for-byte the
registry row and the file on disk — and **D88, D89, D90 and D91 all read the same bytes**. Across
four vintages spanning ten weeks, **all 17 historical board-seasons in all three market series are
identical**, while a positive control on the live 2026 season shows real churn (95 players added,
478 of 482 ranks moved). So no 2020–2025 backtest can depend on vintage, and the brief's
two-vintage comparison is degenerate — D92 did **not** run it and says so.

**Determinism holds too:** rosters and every gate-bearing metric are invariant across
`PYTHONHASHSEED` 0–5 (only `bench` moves, 2.20 points, D89 defect #4); a full retrain reproduced the
board **bit-identically** in all seven seasons.

**Established cause of the D89→D91 difference: the runner was never committed.** Every input
reproduces, the simulation is deterministic, and yet D89's published Y1 behaviour does not come back
in *either* format (target first-RB round 4.15 → 5.27; kickers 3.45 → 2.98; legacy first-QB 1.88 →
2.20). Neither opponent strategy closes the gap. **Which** difference it was cannot be determined —
the code is gone — so no story is offered. **Consequence: D86–D90's draft-layer numbers, including
the +49.0 six phases cite, are not reproducible and should not be quoted as measurements.**

**The fix, committed:** `evaluation/board_vintage.py` (a vintage = upstream board sha256 + identity-
map sha256 + per-season `load_season_projections` hash; `assert_vintage()` makes it a precondition;
20 tests) and `scripts/d92_paired_grid.py` (the grid, versioned, stamping git HEAD, argv, vintage and
measured s/pick onto every result, and keeping the per-pick rankings D89/D90 discarded). Canonical
vintage: `74b2ea7d680ebe4dfdf4f9d98568810f5a43d4bfde7e9e4428fcc46fac33f4de`.

**Baseline on that vintage:** target **+28.0** [−40.7, +96.7] with **94% from 2022**; dynasty
**+31.5** [+4.6, +58.4], all six seasons positive. Cost: Y1 0.032 s/pick, O1 6.249 s/pick (≈195×,
≈6 s live). 2026 unchanged: #1/#20 identical in both arms, first divergence a **0.2-point tie**.

**Next:** re-measure O1 once through the committed runner with `--expect-vintage` — the first
reproducible draft-layer number this project will have — then revisit Option G against it.

### Earlier status: M43 complete (D91) — **The +49 does not survive a market-board refresh (+28.0, 94% of it one season); O1's availability model is nearly inert and the real mechanism is startable-slot count; Y1's marginal value is degenerate across the entire bench. Nothing shipped.**

An architecture diagnosis, not an experiment to ship from. Full report:
`docs/D91_O1_ADVANTAGE_ATTRIBUTION.md`. Ablations pre-registered at `b0342e5` **before any of them
ran**. `models/` and `league/` byte-identical to Y1; `src/` byte-identical to `origin/main`.

**Two premises in the brief were wrong.** D86–D90 are already merged (`origin/main` == HEAD; the
stale ref is the local `main`). And the D86–D90 artifacts **no longer exist** — they are gitignored
and the container was cloned fresh — so "reuse the already-computed paired drafts" was impossible
and the phase split into Track A (arithmetic on committed tables) and Track B (rebuild and re-run).

**The headline finding is about the ruler, not the candidate.** The rebuilt database reproduces
D89 §2.2's weekly rows, board size, uncertainty predictions and consumption demand **exactly**; the
market board does not, because DynastyProcess's `db_fpecr` has gained historical rows. With
identical code, projections and outcomes, the target-format margin goes **+49.0 → +28.0**, its CI
stops excluding zero, the per-season pattern **anti-correlates (r = −0.652)**, and **94% of what
remains is 2022** (drop it and the effect is +1.9). Dynasty moves the other way (+20.8 → +31.5) and
is now the better-behaved format. **The two formats swapped which one clears G8.** D90 §7's
monotone trend (ρ = +0.994) comes out −0.397 — its author flagged it as post-hoc and declined to
claim it, and that caution was right. Pre-registered gate **R0 fails**, so nothing in Track B is
presented as a decomposition of the published +49.0.

**Y1's actual defect, measured** (`scripts/d91_msv_degeneracy.py`): on a roster with all ten
starting slots full, Y1's marginal-starter-value across six bench candidates spans **0.48 points**
(RB 0.00, K 0.00, DST 0.00 …) against O1's 99. Y1 prices the whole bench at zero *simultaneously*,
so rounds 11–16 carry no lineup signal and fall through to daVORP — which D85 measured as
over-valuing K 5.34× and DST 8.10×.

**The ablations.** **A2** (rates → 1.0) reproduces Y1 on all 60 rosters with max |Δ| =
`0.000000000000`, verifying that O1 changes exactly one thing. **A1** (flat pooled rate) retains
**123%** of the effect — **the measured availability data is nearly inert**, and what carries the
behaviour is `P(hole) = 1 − rate^slots`, i.e. pure **startable-slot count** (a fact about the
lineup, not about injuries). **A3 did not test what it was registered to test** — at rate 1.0 a
backup kicker is worth *exactly zero*, below what O1 pays, so it *intensifies* the restraint;
recorded as a design error, and the K-carrier question remains unsettled by any input manipulation.

**Minimum viable change (option G, smaller than A–F):** give `marginal_starter_value` a
non-degenerate, startable-slot-aware value for players who cannot crack the current lineup —
no availability model, no weekly objective, no Monte Carlo, no K/DST special-casing. **Not
actionable yet: instrument before objective.**

**Next question:** pin and version the ECR board as an immutable artifact, then re-run
D84/D85/D89/D90's headline contrasts on two pinned vintages and report the spread.

### Earlier status: M42 complete (D90) — **O1's mechanism reproduces on a second, independent board (kickers 2.40 → 2.00), and the effect is same-signed at +20.8 — but below the economic threshold and unresolved. G7 still fails. Nothing shipped.**

D89's recommendation, executed: run O1 unchanged on a third format whose lineup actually contains
K and DEF slots. 120 drafts. Full report: `docs/D90_CROSS_FORMAT_GENERALIZATION.md`.
Pre-registered at `431e424` **before any result was seen**, with a test asserting D90 differs from
D89 in `phase` and `formats` and in nothing else.

**The format choice was forced by data, not preference.** `market/series.py` derives the board
from `is_dynasty × is_superflex`, so exactly four series exist and two are used. Of the two
candidates, `do` (dynasty 1QB) has 6 usable seasons to `rsf`'s 5 — and **both superflex boards
carry zero kickers and zero defenses**, because FantasyPros' "OP" pages rank offensive players
only.

**That deepens D89's diagnosis.** The legacy format could not test O1 for *two* independent
reasons: no K/DEF slot in its lineup **and** no K/DST players on its board. It was never a weak
test of this mechanism; it was not a test of it.

**The mechanism reproduces on a board sharing no rows with the target's**: kickers **2.40 → 2.00**,
defenses 1.83 → 1.63, RB depth 2.72 → 2.97, TE depth 1.58 → 1.97, first DST a full round later,
early rounds untouched (first QB/RB/WR all move < 0.1 rounds). **O1 draws exactly 2.00 kickers in
every season** — precisely the roster's K capacity — while Y1 ranges 2.00–3.00 and drifts upward.
G5 says it from the legality side: **0 capacity breaches for O1 vs 24 for Y1**.

**The magnitude does not clearly generalise.**

| format | K/DST slots | seasons | effect | 95% CI | improved | mechanism |
|---|---|---|---|---|---|---|
| target_league | 2/2 | 6 | **+49.0** | [+6.5, +91.5] | 5/6 | ACTIVE |
| legacy_2qb_dynasty | **0/0** | 5 | −2.3 | [−85.5, +80.8] | 3/5 | **NOT TESTABLE** |
| dynasty_1qb | 2/2 | 6 | **+20.8** | [−30.8, +72.3] | 4/6 | ACTIVE |

+20.8 sits **below the 25.0 economic threshold**, its CI **spans zero**, and the MDE here is 51.5.
All three metrics are positive (+20.8 / +24.8 / +13.1) and LOSO is all-positive, but **G3, G8 and
G9 fail** in the third format and **G7 fails** overall.

**G7 is not redefined.** Among the two structurally testable formats the sign is consistent — that
is reported as a *diagnostic*, not promoted to a gate, which is exactly what prediction T5 was
written to forbid.

**One unregistered pattern, flagged not interpreted:** `dynasty_1qb`'s per-season effects are
perfectly monotone increasing (−46.2 → +80.2, ρ = 1.00; early half −18.8 vs late half +60.4), and
`target_league` trends the same way. Noticed after the fact, so no p-value and no claim — but a
mean of +20.8 built from a monotone climb is not a stable +20.8, and LOSO cannot see that.

**2026 is unchanged in the third format too**: identical #1/#20/#21 (St. Brown / McCaffrey /
Allen); the only roster difference is Y1's third kicker becoming a fifth WR.

Verdict: **B — promising but unresolved. DO NOT SHIP.** Not C or D: the effect did not reverse and
the mechanism reproduced, so closing O1 would be wrong in the opposite direction. **The reason to
doubt O1 has changed** — no longer "it might be a target-format artifact" but "its benefit outside
the target format is smaller than this benchmark can measure."

**Next:** the documented question is whether O1's benefit is a function of how much K/DST
over-drafting there is to correct, and whether that has been rising — testable on existing
artifacts, since Y1's own kicker count rose 2.00 → 3.00 over the same window.

**Repository note:** `origin/main` does not yet contain D86–D89; those commits live on this
branch (main is at `b9c389d`, which merged D85). Production integrity is unaffected.

### Earlier status: M41 complete (D89) — **six seasons DO resolve O1 in the target format: +49.0, CI [+6.5, +91.5], and all nine in-format gates pass. It still does not ship — the binding gate is now G7 (cross-format), not G8. Nothing shipped.**

D88's own recommendation, executed: add the one remaining usable season and re-run O1-FULL
unchanged. No new objective, no tuning, no new gate. 240 drafts run, 220 analysed. Full report:
`docs/D89_2020_REPLICATION.md`. Pre-registered in
`src/alpha_squad/evaluation/replication_design.py` **before any result was seen**, with a test
asserting D89 differs from D88 in `phase` and `seasons` and in nothing else.

**The question D88 posed is answered YES.** Target 1QB: **+49.0**, clustered 95% CI
**[+6.5, +91.5]** — *the interval excludes zero*. MDE fell 56.0 → **42.5** (effect/MDE **1.15**),
further than D88's forecast of 47.3, because 2020's cluster (+41.3) landed near the mean and
*lowered* the between-season SD to 40.5. **Prediction R2 registered in advance that this was a coin
flip**; an outlier 2020 would have cancelled the gain from the extra cluster.

**The effect is stable**: +52.9 → +50.5 → **+49.0** across three independent enlargements;
D88 → D89 movement −1.5 against a pre-registered ±16.5 threshold. 5/6 seasons improved, LOSO
+40.0 … +60.9, season-long +35.8.

**Reproduction is exact**: all 200 shared cells bit-identical on every gate-bearing metric, 0 roster
mismatches.

**All nine in-format gates pass** — including G1/G4/G5, which D88's table never reported and which
are computable from the recorded rosters. G5 is notably favourable: O1 breaches positional capacity
**31 times vs Y1's 53**.

**G7 is now the sole blocker.** Target +49.0 vs legacy −2.3 — opposite signs, so D86's "clear every
gate" rule ships nothing. **The obstruction moved rather than disappeared: D88 was blocked on
statistical resolution, D89 is blocked on cross-format generalisation.** Legacy is a *null, not
harm* (−0.1% of base, CI [−85.5, +80.8], all three secondary metrics positive) — its lineup has **no
K and no DEF slot**, so O1's mechanism cannot act there and both arms draft zero of each in all 100
drafts. R6 predicted this. But **G7 as written cannot distinguish "null because there is nothing to
act on" from "target-format artifact"**, and that ambiguity is not grounds to override it.

**Two data defects, one of which would have fabricated a season.** (1) Target 2020's preseason board
is `redraft-offense`, not `redraft-overall`; the default returned an empty board and the fair
opponents would have drafted **alphabetically** — fixed before the run, 2021-2026 unchanged. (2)
**Legacy 2020 has no preseason board at all** (`dsf` begins 2020-10-16): Phase 1 validated only the
target series and missed it, the run exposed it, and the cell was **excluded, not repaired**. Hence
target ran 6 clusters and legacy 5. A guard (`EmptyMarketBoardError`) now makes an empty board an
error, because it previously degraded *silently* to alphabetical opponents with legal rosters and
finite metrics.

**Two further defects documented, not fixed**: `compute_league_starters` breaks exact FLEX ties by
`set` iteration order, so `bench_contribution` is PYTHONHASHSEED-dependent (2 cells of 200, ≈4–6
pts; verified by seed sweep; lineup *totals* provably cannot move) — the fix is in `league/`, which
D89 must not touch. And **D88's slot-sensitivity table was arithmetically wrong** (it added
within-variance to an SD that already contained it, contradicting its own CI); the true 5-season
floor is **51.1**, not 56.0 — which *strengthens* D88's conclusion rather than weakening it.

**RB and 2026 unchanged and confirmed**: identical elite-RB sensitivity (both need +75 at #1, vs a
measured ≈+47.7 bias), identical 2026 #1/#20/#21, first divergence round 11.

Verdict: **B — promising but unresolved, obstruction relocated.** Not A (G7 fails; and the CI's
lower bound +6.5 is below the 25.0 economic threshold). Not C (nothing collapsed; 9/9 in-format
gates). Not D (legacy is a null, not material harm). **The objective is no longer the weak link** —
what blocks it is that the benchmark holds exactly one league in which its mechanism can act.

**Next: add a third league format that DOES have K/DEF slots and re-run O1 unchanged.** That turns
G7 from an untestable constraint into a real test, and either outcome is decisive. Not a new
objective, not more seasons, not more slots.

### Earlier status: M40 complete (D88) — **O1 replicates at 2.5× the data (+50.5), and draft slots provably cannot resolve it: the MDE floors at ~56 against an effect of ~50. The binding constraint is seasons, not slots. Nothing shipped.**

The power/replication experiment D87 recommended: O1-FULL at 10 draft slots, full board, no
shortlist, same objective/opponent/seasons/metrics/gates. 200 drafts. Full report:
`docs/D88_O1_POWER_REPLICATION.md`.

**Reproduction is exact.** Slots 1–10 superset D86/D87's four, and that subset reproduced
identically in both formats (+52.9 / +1.6, same rosters, same metrics to the decimal).

**The effect replicates.** Target 1QB **+50.5** (was +52.9), season-long **+39.9**, **4 of 5
seasons improved**, LOSO all positive, 0 unfilled slots. Legacy remains a null (−2.3).

**The decisive finding is a power result.** Between-season SD is 45.1 and within-season SD 55.7, so
the clustered SE is `sqrt(45.1² + 55.7²/n)/√5` — slots shrink only the second term. MDE goes
65.8 (4 slots) → **60.1 (10 slots)** → 58.1 (20) → **56.0 (∞)**. **The effect (+50.5) sits below
the asymptote, so no number of draft slots can ever resolve it.** D87's recommended experiment was
correctly designed and was never capable of succeeding; D88 proves that rather than assuming it.
Six seasons would give MDE ≈ 47.3, and **exactly one more season is available** (2020; 2019 has no
established-player projections) — a ~3-point margin, a coin-flip.

**K/DST survives at scale**: kickers drafted 3.74 → 2.62 (4-slot measured 3.70 → 2.60). Early
rounds are untouched (first QB/RB/WR identical to two decimals); all the difference is the
endgame. The mechanism is confirmed in realized utility — O1 accumulates *fewer* raw roster points
(−19.8) while converting more into lineup points and bench contribution.

**The RB hypothesis is closed**: O1 and Y1 have *identical* elite-RB sensitivity (both need +75 at
#1, neither moves at #20/#21). Weekly roster utility gives no protection against the known
under-projection.

**2026 #1/#20/#21 are identical under both arms**; first divergence is round 11, where Y1's third
and fourth kickers become a RB and a TE.

Verdict: **B — promising but unresolved, obstruction identified.** Nothing ships; target fails G8
alone (by 5.5 points), legacy fails G3/G6/G7/G8/G9.

### Earlier status: M39 complete (D87) — **the K=10 shortcut is not a faithful approximation: ranked by Y1, it re-imports Y1's K/DST over-valuation into O1 and flips sign across formats. Nothing shipped.**

A controlled replication/efficiency test of D86's O1. Full report:
`docs/D87_SHORTLIST_REPLICATION.md`.

**A baseline discrepancy was diagnosed first.** The D87 brief cited "O1 K=40 = 6.26 s/pick, O1
K=10 = 0.51 s/pick"; D86 actually measured 6.26 s/pick for the **full board** and 0.51 s/pick for
**K=40**, and K=10 was never tested. D86's +52.9 therefore belongs to **O1-FULL**, and the
experiment was run against that.

**K=10 changes 10.3% of decisions in the target format — but 0.0% in rounds 1–7 and 18.3% in
rounds 8–16**, exactly where O1's mechanism operates. All 33 changed decisions had the full-board
pick outside the cheap top-10 (median cheap rank 205), and they substitute K/DST for skill players
(TE→K 13, RB→K 5). The cause is structural: **the shortlist is ranked by Y1**, which D85 measured
as over-valuing K 5.34× and DST 8.10×, so in rounds 12–16 the Y1 top-10 contains a kicker 90–100%
of the time. Kickers drafted go Y1 3.70 → O1-FULL 2.60 → **O1-K10 3.25**, and O1-K10's 2026 roster
is composition-identical to Y1's, four kickers included.

**O1-K10 passes every target-format gate (+62.3, CI [+16.1, +108.6], 0/5 seasons worse) and then
fails G7**, flipping to −7.1 in `legacy_2qb_dynasty` — the only arm to change sign, where O1-FULL
held (+52.9 / +1.6). The margins are also **non-monotonic in K** (+62.3 / +41.9 / +52.9), which
with no supporting mechanism marks them as noise. Cost was never the binding constraint: even the
full board answers one pick in ~5 s.

**This changed the next step rather than confirming it.** D86 recommended re-running O1 at 10 slots
and the affordable route looked like the shortlist; D87 shows that would have measured a different
policy. The corrected recommendation is **O1-FULL, no shortlist, 10 slots, both formats** (~2.2 h
per format). General lesson: a shortlist must be validated for the *behaviour* under test, not
merely the selected player, and must not be ranked by the engine whose bias the expensive
objective exists to correct.

### Earlier status: M38 complete (D86) — **the objective itself was wrong: it scores season totals and therefore prices the bench at zero, when the bench supplies 17.8% of realized points. The fix is real, generalises, and still fails the gates. Nothing shipped.**

D85 closed the value-base seam. D86 asked the prior question — *what should Alpha optimize?* — and
found the defect is the **metric**, not the formula. Every published draft number scores a roster
from season totals with one lineup allocation; fantasy scores weekly, so the incumbent objective
cannot see a bye, cannot see an injury, and gives the bench a value of exactly zero. Measured:
bench = **17.8%** of realized points (no-foresight lineups), and a bench player starts in **16.2 of
17 weeks**. Full report: `docs/DRAFT_OBJECTIVE_RESEARCH.md`.

**A retrospective oracle over 320 real pick states decides the phase.** ~90% of the gap to a
retrospectively optimal pick is luck (realized-points gap 104.1 of 116.2 mean regret; Spearman of
Alpha's score against final realized roster value = **−0.033**). **One pick moves the final roster
by ~2.6%.** The *structural* residual — picks where the oracle's player scored no more and still
won — is 16 of 320 and worth **~90 points per draft**, against D71's ~128-point minimum detectable
effect. **The prize is smaller than the ruler.**

**The candidate is the strongest this project has produced and still does not ship.** O1
(`E[weekly msv] + daVORP`, availability rates measured walk-forward, no bonus anywhere) scores
**+52.9** on the primary weekly metric and **+34.5** season-long in the target format, cuts kickers
drafted from **3.70 to 2.60**, and is the first candidate in nine to keep the same sign in both
formats. It fails **G8 alone** in the target format (CI [−8.3, +114.0]) and is an effective null in
`legacy_2qb_dynasty`, which has no K/DEF slots for the mechanism to act on. On the 2026 board it
makes the **identical** picks at #1/#20/#21 and replaces Y1's third and fourth kickers with a RB
and a TE.

Four of six pre-registered predictions missed and are recorded as misses. Replacement level is
**validated** rather than changed (the incumbent tracks the no-foresight waiver replacement at
every position; streaming is real but unmeasurable — there is no transaction history). O1 costs
180× a control pick naively, but a **K=40 shortlist reproduces the identical pick at ~7s per
draft**, which is production-feasible — and which makes **re-running the identical pre-registered
arm at the full 10 slots** the highest-value next step, requiring no new idea.

### Earlier status: M37 complete (D85) — **economic valuation and roster legality are already separate; the value-base correction is mathematically right, behaviourally correct in every format, and unshippable. Nothing shipped.**

D84 closed by naming one remaining direction: roster legality as a hard constraint on the
candidate pool, measured **jointly** with its arm C, because "the double count and the legality
guarantee are currently the same mechanism". D85 ran that as a pre-registered 2x2 (Y1 vs corrected
valuation) x (legality off vs on), gates imported from D84 rather than restated, predictions
recorded in advance. Full report: `docs/VALUATION_LEGALITY_SEPARATION.md`.

**The premise did not survive.** The legality constraint provably works — on a constructed state
it changes the pick — and **never fires once in 800 real picks** under either valuation. Arm C
produces **zero** infeasible rosters here against D84's 2, so D84's "the over-valuation is
load-bearing for roster legality" is board-specific, not structural. The interaction is **exactly
+0.00** in all four formats tested. The two mechanisms were never entangled.

**A new mathematical result closes the seam.** `d(value_base)/d(proj) = 2.000` under Y1 **and
under the correction**, at every position: arm C subtracts a per-position *constant* (`Y1 - armC =
R_p` exactly) and fixes the level, not the slope. The only unit-slope formulations are the two
already measured and rejected three times, and they lose because halving the value base against a
static-VORP opportunity cost re-weights every position (the scale mismatch open since D60). No
reformulation inside `(value_base + oc) x multipliers` can have both the D63 scale and a correct
slope.

**The correction generalises; the benefit does not.** It defers QB in 1-QB (first QB 2.12 -> 3.04)
and leaves superflex alone (1.56 -> 1.54), defers K (~8.8 -> ~10.4) and DST (~10.0 -> ~13.0) in
every format that has them, and flips #20 on the 2026 board from Josh Allen to Jeremiyah Love.
Starter points: **+26.6 target, -9.1 legacy 2QB, -4.4 superflex, -11.1 2QB redraft**; clustered CI
[-72.5, +125.7]; 2 of 5 seasons worse. Fails G3, G7, G8. **Nothing ships.**

**RB (mandatory) is both layers.** Elite-ECR RB signed error 2022-2025 is **+47.7**; Y1 needs
**+75** of correction before it takes an RB at #1 (McCaffrey at 351.7, independently reproducing
D84's "~350"), the correction needs **+50**, and at #20 the RB projection is irrelevant under
either up to +100. Opportunity cost works *against* elite RBs at the top. No RB projection was
modified.

**One silent harness defect was found and fixed before it produced a false result** (`ab5a1aa`):
the L-tiers were omitted from the draft-aware replacement dispatch, reverting every arm to the
static level (the D65 defect) and putting the control 79 points below its own known value. Caught
by the pre-registered "L0 must equal Q0" check; all six controls now agree to four decimals in
both formats.

This is the **ninth** value-base reformulation measured. D71's ~128-point MDE is confirmed again:
**no draft-layer value-base change can be established or refuted at this data scale.** Resolving
it needs a better objective — one that prices bench depth, injuries, byes and waiver leverage —
not another value base.

### Earlier status: M35 complete (D78) — **the reported projection "compression" was investigated and is mostly correct behaviour; a real training-specification defect was found, pre-registered, measured and shipped; and a production-blocking DST bug was found and fixed.**

A pre-draft report said the 2026 projections were materially miscalibrated, particularly at RB
(top projected WR ~316 against ~3-4 real 2025 WRs above it; top projected RB ~251 against ~10-11).
Both figures reproduce. Their interpretation does not survive measurement: `E[max Y] > max E[Y]`
for any noisy outcome, and against M6's own out-of-sample residual distribution the observed
exceedance count is **inside the model's 90% predictive band in 18 of 20 position-seasons** — 2025
RB is 11 observed against 13.0 expected, band [9,17], i.e. the model expected *more* than happened.
The only genuine outlier in 2021-2025 is 2024 RB. The cross-positional part is real (RB−WR
top-decile gap +98.8 in 2024, +123.3 in 2025) but trending rather than stationary, and **the
FantasyPros expert consensus makes the identical error** (RB top-decile bias +38.96 market vs
+39.21 model over 2022-2025). Naively raising the top of the board is measurably worse.

Nine candidate model changes were measured walk-forward and rejected. **Two defects in M6's
training specification did hold up** — the ECR sentinel 999 doubling as "no board existed this
season" (2016-2019), and the point model never training on season S-1 — and were tested under four
arms and seven gates pre-registered in git before the run. **Y1 shipped**: real backtest MAE
42.31 → 40.88, RMSE 59.09 → 57.09, Spearman 0.757 → 0.770, better in all five seasons and at all
four positions, with conformal coverage moving 0.7901 → 0.7971 against a 0.80 target. Y3 scores
better and clears every gate but was **not** taken, because the selection rule was fixed in advance
and Y2 (the component Y3 adds) fails G6 alone. No positional term of any kind shipped; D68/D69/D70
stay closed.

Separately, the new `train projection-status` gate immediately exposed a production-blocking bug
that had nothing to do with projections: `make` ran `features` before `team-scores`, so the K/DST
step joined an empty `team_week_points` and wrote **zero DST rows in every season** — a league
starting a DEF would have scored zero for that slot, silently. Fixed at the dependency, with the
counts now printed and a hard error rather than a quiet zero.

**The draft-layer contrast is a null.** A paired variant-vs-control run on identical trials
(5 seasons x 4 slots, 40 drafts per arm) puts Y1 at **-15.8 starter points, W/L 10/10,
season-clustered 95% CI [-89.2, +57.6]** against the v1 specification. A measurable
projection-accuracy gain did not translate into a measurable drafting gain and may have cost a
little. Y1 stays shipped because D78 pre-registered projection-layer gates only and it cleared
every one; reverting on a post-hoc non-significant negative would be the after-the-fact
selection this project has refused six times. The claim is therefore narrow: Y1 is more
accurate, and is NOT demonstrated to draft better. The first run of that contrast returned a
perfect +0.0/50-ties null which was a HARNESS DEFECT, not a finding -- `recommend_draft_pick`
reloads the board itself and both arms scored on the same projections; the fix and the
"assert the arms diverge before interpreting" check are recorded in D78 section 8c.

`make project-current-season` produces and verifies the upcoming season's board (610 established +
150 rookie + 74 K/DST rows; the application's own loader returns 834 players across all 6
positions). #2 (overall pick numbers with correction) and #3 (one source of truth for roster
state) shipped, along with three real UI bugs found by driving the app in a browser — the most
serious being the Draft view sitting on season 2025 while 2026 projections existed. **P1-0b
remains OPEN** as the standing measurement limitation D71 reclassified it to; nothing in this phase
changes that, and the season universe is still n=5.

### M36 (D79-D83) — the draft-decision and projection investigation. **Nothing shipped to the model.**

One production defect was found and fixed (D79): `GET /rankings` served the wrong universe —
163-179 players missing per season, including **every K and DST** — which also broke
`league/draft.py`'s `pool_is_a_board` guard, so D67's draft-aware replacement never engaged in
production (RB-vs-WR replacement gap −0.4 static against +31.1 draft-aware). The served universe
is now verified identical to the engine's in every season 2021-2025.

Everything else was measured and rejected. **Thirteen pre-registered candidate models across three
phases** (D80 top-of-board arms, D82 feature addition, D83 seed ensembling) were tested against
gates committed to git *before* any arm ran, walk-forward on 2022-2025. **Every one failed.** The
closest — a 24-seed ensemble — confirmed its own pre-registered mechanism prediction (WR top5
−7.62 MAE, gains scaling with seed count, 7 of 9 gates passed) and was then measured on realized
starter points: **−7.9, season-clustered 95% CI [−101.9, +86.1]**, 2 of 4 seasons, median paired
difference exactly zero.

The common cause is now measured. Varying **nothing but CatBoost's random seed**, the shipped
model's predictions move **9.66 points in the head of the board against 2.42 in the body** — the
top is four times less determined by the data than the rest, before any change is made. It is
**variance-limited, not information-limited**, which is why changing the estimator (D79/D80) and
changing the information (D82) both failed.

**The WR-heavy opening is a decision-engine property, not a projection-model property**, on three
independent lines: elite RBs must project ~350 (about 140 points above the training data's own
answer of 210.3) before one is taken at #1, and no value changes picks #20 or #21; no projection
change clears the gates; and the one candidate that measurably improved top-of-board accuracy made
the WR concentration *worse* (first-pick RB 8/40 → 0/40) at no gain. The open question is the
decision layer's value base — `msv + daVORP` counts raw projection twice at an empty roster slot,
and QB replacement is drawn at the *consumption* boundary (QB22) rather than what a 1-QB roster
starts. Full report: `docs/PROJECTION_INVESTIGATION_FINAL.md` and
`docs/OPENING_DRAFT_AUDIT.md`.

Earlier milestone history (M0-M34) is unchanged and summarised in the table below.

| Milestone | Status | Notes |
|---|---|---|
| M0 Bootstrap | DONE | project skeleton, deps, docs |
| M1 Sources + snapshots | DONE | 7 adapters (4 available, 3 blocked/no-creds), all verified live; 25 offline + 6 network tests passing; one real bug found and fixed in review (see below) |
| M2 Canonical identity | DONE | player_id spine (25,046 players) + 25 crosswalk ID types + college bridge, all verified against live data; 43 offline + 8 network tests passing; three real bugs found and fixed in review (see below) |
| M3 As-of features + leakage | DONE | games/player_week_stats/player_week_features (199,632 rows over 2015-2025, built in ~7s from cache); leakage-safe by construction via SQL window frames; 51 offline (incl. 12 leakage tests with independent Python recomputation) + 9 network tests passing |
| M4 Baselines + evaluation | DONE | 3 baselines (previous-year, weighted-2yr, ECR-implied) walk-forward evaluated 2018-2025 against 21,421 real player-seasons and 210,730 real market snapshots; shared evaluation harness (MAE/RMSE/R²/Spearman/top-N hit rate/tier accuracy) reused by every later milestone; 65 offline + 10 network tests passing. **One number in this milestone's report was wrong and got corrected in M5 — see D19.** |
| M5 Established-player ML | DONE | Position-specific Ridge/CatBoost/XGBoost + opportunity-only + team-environment-only + ensemble, both weekly (in-season) and season-level (preseason, apples-to-apples vs M4); team_week_stats/features extend the M3 panel; model_registry tracks version/validation; 70 offline + 12 network tests passing. One real evaluation-harness bug found and fixed (D19), affecting M4's reports too. |
| M6 Uncertainty + calibration | DONE | Split-conformal p10/p25/median/p75/p90 + Monte Carlo top-12/24 probabilities on the M5 season-level CatBoost model; walk-forward 3-way split (train/calibrate/target) so calibration is genuinely out-of-sample; real measured coverage_10_90 mostly 0.72-0.90 (target 0.80) across 2019-2025/QB-RB-WR-TE — legitimately well-calibrated, not just plausible-looking; 82 offline + 13 network tests passing |
| M7 Rookie/prospect intelligence | DONE | Draft capital + combine + prior-season landing-spot features (college production LIMITED — D20 found no verified ID bridge to cfbfastR; D38 built a real CFBD/espn_id-bridged one, and **D39 measured it and did not adopt it** — neutral-to-worse on every metric, so the production feature set stays at the 12-feature D20 baseline); CatBoost regression (rookie-year PPR) + classifier (top-24 breakout, Brier-scored) walk-forward by draft class; nearest-neighbor historical comps; 1,077 real rookie-seasons, 88 offline + 15 network tests passing; two real bugs found and fixed (combine height stored as "6-0" string, comps dtype crash) |
| M8 Market + EDGE | DONE | market_snapshot extended to ro/do/rsf/dsf (2QB-aware); dynasty_values (681 real players, 97.6% identity coverage); EDGE (rank/points/probability edge, BUY/HOLD/SELL/WATCH) gated so a raw rank discrepancy alone can never produce BUY/SELL (D21); historical EDGE validation shows the real BUY cohort beat market-implied points in 3 of 4 scored seasons 2022-2025 (recomputed in M13 after a data-correctness fix — see D28 — numbers below reflect the M13-era figures); 102 offline + 18 network tests passing (both suites reran clean end-to-end after this milestone) |
| M9 Evidence engine | DONE | 4 real Strong-tier detectors (depth-chart move, injury self/teammate-opportunity, roster transaction, usage-share shift) on officially-sourced nflverse data; 33,311 real events across 2019-2025; bounded (±15%) evidence-adjusted weekly projections, never overwriting the base M5 prediction; wired as a real (mostly-neutral-in-practice) veto into M8's EDGE gate (D23); 123 offline + 21 network tests passing (verified via `pytest -m "not network"` / `-m network` directly, not estimated) |
| M10 League decision engine | DONE | Real value-based-drafting replacement/scarcity derived from the league's own lineup config (verified: 2QB target league produces 20 real dedicated QB starters on real 2025 data, exactly 10 teams x 2 QB slots); draft/waiver/dynasty-trade recommendations with alternatives, roster fit, next-pick survival probability, and real evidence-driven value-spike bidding; the M7 rookie-prediction fallback was confirmed live against a real rookie-only player; 152 offline + 26 network tests passing |
| M11 Agents/orchestrator | DONE | Pydantic Task/Result/Evidence/Prediction/Edge/Decision contracts mirroring AGENT_CONTRACTS.md; 9 real agents (thin wrappers around already-validated M1-M10 code, never an LLM call, D14); DAG orchestrator with real dependency resolution, retry/backoff, and genuinely concurrent scheduling (proven: two independent tasks start within 0.2s of each other) with DB-write serialization for correctness; disagreement protocol reusing real M8/M4-M5 data (296 real disagreements detected on 2024/2025 data, both positions always preserved); a real DuckDB concurrent-DDL bug was found and fixed via the orchestrator's own test suite (D26); 172 offline + 29 network tests passing |
| M12 API + frontend | DONE | FastAPI over the real M1-M11 pipeline (8 routers, every field a direct projection of an already-persisted table or an M10 function call, zero parallel logic); React+Vite+TS SPA (6 real, live-data views); verified end-to-end in a real Chromium browser via Playwright against real persisted data, including the literal Gate 8 test (killed the API process, reloaded, confirmed a real fetch error rather than stale/fabricated content); 189 offline + 33 network tests passing |
| M13 Hardening | DONE | correlated team-season Monte Carlo simulation (D8 deferred item, `models/simulation/`); found and fixed a real cross-cutting data bug affecting M4-M10 (postseason games silently pooled into every "season" aggregate since M3, D28) — rebuilt the affected tables and retrained every downstream model; found and fixed two simulation-design bugs (QB anchored to the wrong shared variable, a share-denominator mismatch, D29) plus a real RNG-reproducibility bug; fixed a stale README/Makefile and added CI (D30); wrote docs/TRACEABILITY.md; 204 offline + 37 network tests passing |
| M14 Post-audit hardening | IN PROGRESS | Working the `docs/CURRENT_STATE_AUDIT.md`/`docs/IMPLEMENTATION_GAP_ANALYSIS.md` P0-P3 backlog. **P0** (security): D35's history-rewrite decision was already made and declined by the user at the time -- not reopened; added a durable CI guardrail (`scripts/check_no_secrets.py`, D42) instead. **P1-1** (UI wiring, D44): waiver/trade/roster-need wired into the SPA, live-verified against a real Sleeper league. **P1-2** (EDGE backtest, D41): `alpha-squad edge backtest` + `reports/edge_backtest.md`, real per-position/bucket breakdown, BUY beat market in all 4 scored seasons 2022-2025. **P1-3** (model persistence, D43): `models/persistence.py` closes the audit's single biggest architectural finding (no model was ever saved to disk) for the two paths that actually serve live predictions (uncertainty → `/rankings`, rookie projection → `/rookies`); verified against the real database. **P2** (dynasty future-pick valuation, D45): `pick_value`/`evaluate_trade_package`, a documented heuristic anchored to real `dynasty_values` data, verified live. **P4+P5 together** (evidence → served intelligence + in-season/ROS, D46): re-read PRODUCT_SPEC.md/ARCHITECTURE.md to confirm evidence should reach served output (not just gate EDGE); ran the real weekly established-ML pipeline (never before executed in this deployment) and the evidence-adjustment pass against real 2025 data, then added `GET /rankings/weekly` + a UI mode — verified live in a real browser with a real evidence-driven adjustment rendered. **P7** (orchestrator task decomposition, D47): `agents/planner.py::plan_full_refresh` builds the real multi-stage task graph from a high-level goal (agent selection + correct dependency edges, read off what each agent's code actually queries/writes) instead of every caller hand-typing one; `alpha-squad orchestrate run` verified against the real database with genuine `rookie_ml`/`projection_ml` concurrency and correct `market_edge` ordering. **P8** (application hardening, D48): `GET /seasons/latest` + a shared `useLatestSeason` hook so every view defaults to the real newest season instead of a hardcoded one; `PlayerPicker.tsx` makes the previously-dead `GET /players` reachable from Waiver/Trade, fixing a real HTML `<label>`-click-forwarding bug found live. **P1-4** (simulation UI, D49): `POST /simulate/team-season` + `SimulationView.tsx` — the last of the four "built but invisible" capabilities (waiver/trade/roster-need/simulation) identified at the start of this hardening pass, now all closed. Verifying it live surfaced and fixed a real gap: `team_week_points` was empty in this deployment because `build_team_week_points` had never been wired to a CLI command; added `alpha-squad features build-team-scores` and ran it for real (7,326 rows). 303 offline tests passing (up from 262 at audit time). **P3-1** (stale CLAUDE.md data-source note, D50): re-verified live against a fresh `alpha-squad sources status` run (Sleeper/FantasyPros/CFBD all AVAILABLE) and rewrote the note to match `docs/DATA_SOURCES.md`. **P3-2** (expert-accuracy weighting, D51): re-confirmed live that even the paid FantasyPros API exposes only consensus statistics, never per-expert identity; measured the coarser proxy the data does permit (`ecr_best`/`ecr_worst` dispersion) against 1,925 real player-seasons and found no consistent relationship with market accuracy (reverses sign between rank tiers) — not adopted, per the same measure-and-reject standard D39 established. Remaining backlog: P2-3 (network suite in CI), which needs a user credential decision and is the only item left that isn't autonomously actionable. **Final validation** (D52): re-ran the full live/network integration suite against real external services after the whole pass — 41 passed, 1 pre-existing skip, 0 failures — reconfirming every live-source claim made across D41-D51, not just trusting nothing broke. |
| M26 Draft-aware replacement | DONE | D67. Plan-mode diagnostics refuted D66's own recommendation: a uniform demand-depth multiplier is a positional re-weighting whose effect size is set by projection-tail shape (at x2.5 it hands RB +120.4/QB +108.9/TE +106.4/WR +92.0 but K only +30.4 and DST +10.7, because there are ~225 WRs and exactly 32 DSTs). Replaced it with a target that has no free parameter — the demand one mock draft of this league on the preseason consensus board actually consumes, summing to `roster_size` by construction. Pre-registered W0-W4 in git before running; W1 cleared every gate (+32.1 over N4, CI [+11.5,+52.7], LOSO positive on all five, cap breaches 34->1) and beat the D66 x2.5 reference (+26.7) on both the primary metric and out-of-format (+75.5 vs +65.6 on `legacy_2qb_dynasty`). W3 proved the roster-legality constraint contributes exactly 0.0 — it never fires — so it did not ship. Official benchmark: **-5.6 -> +26.5 vs fair consensus**, 4 of 5 seasons won, deterministic across two processes, but not statistically significant. Also fixed a real bug this change introduced (a client shortlist read as a draft board collapses every position's demand to zero) with two structural guards, both verified byte-identical on real data. |
| M27 Projection calibration | DONE — nothing shipped | D68: five pre-registered walk-forward calibration arms (none / additive / affine / rank-band / EB-shrunk) measured on the projection layer over treated seasons 2023-2025. Every arm improves MAE and RMSE; **no arm clears gates G1-G4**. RB's bias is sign-stable and falls under every arm; QB/WR/TE flip sign between seasons, and every G3 failure is at TE or WR. Leakage guard is structural (`fit_arm` raises on a training row at or after the target season). 55 new unit tests. Production untouched: `league/draft.py` byte-identical to D67. P1-0 unchanged and still OPEN. |
| M28 RB calibration assessment | DONE — abandoned, nothing implemented | D69: assessed the RB-only arm D68 deferred, and abandoned it **before implementation**. No estimator was fitted, no arm was run, no draft-layer or benchmark experiment was executed. Grounds: (1) RB sign stability is a mean-only property — 2021 median −12.3, 10%-trimmed −1.5, and the mean itself flips at a top-40 cut in 2022; (2) magnitude is not usefully forecastable walk-forward (best predictor MAE 16.3 vs 14.4 SD of the truths and ~11.2 for an oracle constant); (3) the leading **but not demonstrated** mechanism is an association with an RB-specific availability trend (corr +0.70–0.80 with games played every season; RB mean games +2.52 over 2021→2024 vs WR +0.35, QB −0.04), which a backward-looking estimator lags and which already reversed in 2025; (4) the W1 engine is near-inert to the only supported form — a uniform additive RB shift moves the RB replacement level by the identical amount, so ΔVORP is exactly 0.00 and only 0–2 of the top-20 pick-1 slots change. Winner's-curse / projection-rank conditioning, a market-varying universe, and regime change remain open alternatives. Replaced by a design-only pre-registration for RB availability modelling (`docs/RB_AVAILABILITY_PREREGISTRATION.md`). Production byte-identical to D67. P1-0 unchanged and still OPEN. |
| M29 RB availability features | DONE — tested, rejected, nothing shipped | D70: implemented exactly D69's own recommended follow-up (four preseason-knowable features -- prior-3-season games history, age, position-cohort games baseline, prior-season workload -- appended to M6 for RB only, QB/WR/TE/K/DST untouched). Committed before fitting, same protocol as D67/D68/D69. A real population bug (RB universe collapsed to n=3 by ranking across all positions) was found and fixed BEFORE any valid gate result existed, same category as D68's shrinkage fix. Final, correct result: **B1 (accuracy) and B2 (targeted bias falls) both FAIL** -- RMSE marginally worse (88.60 vs 88.08) and, decisively, the RB signed bias grew larger under treatment in ALL THREE treated seasons rather than shrinking. B3 (availability predicts realized games out-of-fold) passed but weakly and declining (+0.226/+0.176/+0.051 across 2023-2025) -- a materially harder and more honest test than D69's own within-season correlation (+0.70-0.80), and the gap between them is itself informative. Per the pre-registered protocol the draft layer (B4-B9) was never run. Nothing shipped: `league/draft.py`, `league/replacement.py`, `models/uncertainty/run.py` byte-identical to D67. 52 new tests total across D70. P1-0 unchanged and still OPEN. Both of D69's proposed RB paths (calibration, features) are now closed. |
| M30 Benchmark power/variance re-specification | DONE — docs only, no code/model/simulation change | D71: read-only audit of why D61-D70's CI-excludes-zero gate on P1-0 has not moved in nine cycles. Found the 50 `draft_simulation_results` trials are a deterministic `(season x slot)` cross-product, not 50 iid draws -- within a season all 10 slots share one projection set and market board, and Alpha's 10 per-season rosters overlap 53-73% (ICC 0.0995, effective n ~26; the honest unit is the season, n=5). D67's published CI [-38.0,+91.0] is the naive-iid interval; the season-clustered CI is the wider [-100.4,+153.4] (df=4) -- a correction, not a relaxation. Resolving +26.5 needs ~116 seasons at current precision or ~61 even with a hypothetically perfect within-season measurement, against a season universe hard-bounded at 2021+ (`market_snapshot` has no `ro`/`redraft-overall` Jul/Aug rows before 2021) growing 1/year -- no additional slots, reruns, or historical seasons can supply it. **P1-0 split**: P1-0a (roster-balance defect) CLOSED on 0/50 unfilled mandatory slots; P1-0b (absolute superiority) stays OPEN, reclassified as a standing measurement limitation rather than a blocking gate. Future engine work evaluated by variant-vs-control contrast on identical trials instead (D65 Candidate C precedent: CI [+2.3,+44.1]). No RB/WR/QB work reopened; `league/draft.py` untouched. Full account: `docs/DECISIONS.md` D71. |
| M16 Empirical validation | DONE | 8 evaluation modules; headline result unfavourable and reported as such (D54). |
| M17 Draft-engine forensic audit | DONE | Diagnostic only; 400-draft tier ablation; `positional_scarcity` measured and rejected. |
| M18 Positional opportunity cost | DONE | D55; +112.9 starter pts; RB=0 10/50 → 2/50. |
| M19 1-QB format retarget | DONE | D56-D60; market-series fix, K/DST data, flex-aware capacity, marginal starter value shipped. **Its headline benchmark claim is retracted at D61.** |
| M20 Draft-strategy forensics | DONE | D61. Found the benchmark's consensus opponent forfeits its K and DEF starting slots (worth +245.3 pts, more than the whole margin); against a fair opponent Alpha is −48.3, 25/50 (simulated estimate). Diagnosed the mechanism (MSV replacing VORP discards positional scarcity: 68% round-2 QB, first RB at round 5.24, DST at round 10 in 100% of drafts). Found two measurement defects (forensic feasibility cap ≠ production; attribution measured the wrong engine). No engine change made — see `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`. |
| M21 Stage 1 measurement fix | DONE | D62. Shipped the roster-aware consensus opponent (`market_consensus_roster_aware`, both opponents reported side by side, kept `market_consensus` byte-identical), reconciled the forensic/production feasibility caps, fixed `pick_attribution.py` to measure the shipped D60 engine, and scoped `next_pick_survival_probability` by `page_type`. Re-ran the official benchmark on real 2021-2025 data (500 drafts): Alpha vs the fair opponent, measured directly (not simulated) — **−45.4 starter pts, 25/50, 95% CI [−117.1, +25.6] includes zero** — confirming D61's simulated estimate to within 3 points. Determinism verified byte-identical across two separate processes. Stage 2/3 of `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md` not started. |
| M22 Value-base ablation | DONE | D63. Stage 2: found the forensic harness still ran the pre-D61 unaware opponent; fixed, then re-ran the M-tiers. MSV does beat VORP undistorted (+62.6), but the Stage 1.2 cap fix flipped the M-tier ranking — M1 (vorp+msv) 2029.2 now leads M3 (msv) 1989.3, so D60 selected the wrong tier under the diverged caps. Stage 3: 500-draft N-tier ablation under a rule pre-registered in git before any run. Winner N4 = `msv + 1.0*VORP`, +39.9 over the shipped formula, CI [+9.1,+70.6], 37/50, all four gates passed, survives leave-one-season-out. Both clamping alternatives LOST (min -46.9, msv-over-replacement -48.6). Opportunity cost re-measured and kept (helps significantly on 3 of 5 bases). Official benchmark: -45.4 -> **-5.6** vs fair consensus, floor up 1570->1765, stdev 160.8->131.7. Known regression reported: the blend over-drafts kickers (K cap breached in 32/50 drafts), which no pre-registered gate checks. |
| M23 Kicker-hoarding refinement | DONE (no change shipped) | D64. Traced a real hoarding draft pick-by-pick and found the documented diagnosis only partly right: late in a draft MSV is 0 for every candidate, so the value base collapses to VORP, and VORP's STATIC league-wide replacement level makes stripped skill pools look below-replacement (RB -135.6, WR -123.0) while the untouched kicker pool stays above it (+30.1). Flex-eligibility is the second-order cause. Hypothesis B (tighter over-cap multiplier) is provably inert -- the 2nd kicker is taken while UNDER the cap, and margin was exactly +0.0 with a 0/0 W/L record. Hypothesis A (saturate the VORP surplus) lost 32.9 pts and swapped kicker hoarding for QB hoarding; its repaired form R4 fixed roster shape dramatically (breaches 34->4, K 2.74->1.12, RB 2.20->4.00) but scored only +1.3 (CI [-32.0,+34.6]) while LOSING 27 of 50 drafts, failing Gate 3, LOSO and the new Gate 5. **N4 kept; production unchanged.** Next step identified: draft-aware replacement levels. |
| M24 Draft-aware replacement study | DONE (no change shipped) | D65. Confirmed in code that `available_player_ids` never reaches the VORP calculation, so the replacement level is constant across a draft. Quantified the staleness on real data: at round 13 the static level is +178 too high for QB and +69 for WR but only +2.2 for K -- the engine under-values skill positions rather than over-valuing kickers. MSV hits 0.0 at round 11 in all four traced drafts; rounds 11-16 carry 16.1% of realized starter points. Also disproved D64's premise: the 2nd kicker is worth +27.4 pts (17/18 drafts) but the 3rd/4th are worth EXACTLY 0.0 (0/32), capping any kicker-driven gain at ~+4.7 -- inside the noise. Tested three draft-aware definitions; **Candidate C (hybrid capacity) gained +23.2 over N4, CI [+2.3,+44.1], LOSO-robust on all 5 seasons, zero cap breaches, and reached +17.6 vs fair consensus** -- the first positive number ever measured. Not shipped: Gate 3 fails (worse in 2 of 5 seasons; loses 0/10 in 2024), traced to a systematic TE-to-capacity loading whose payoff is season-dependent. Next: pre-registered phase on Candidate C's demand target. |
| M25 Demand-target refinement | DONE (no change shipped) | D66. Found why C3 loads TEs: `startable_slots` counts each FLEX slot once per ELIGIBLE position, summing to 14/team against a 10-starter lineup, so C2/C3 demand 140/220 league-wide players for 100 real slots. Measured: WR wins all 20 flex slots in all 5 seasons, TE wins zero, so true TE demand is 1.00/team vs C3's 4. **The obvious fix was wrong**: both pre-registered repairs lost badly (C5 earned-starter -37.2 with the WORST breaches at 60; C4 ded+1bench -52.4), because a shallow demand target exhausts (C5: 17% of picks) and collapses VORP to zero. The flex over-count was acting as a depth buffer. A 1-D sweep on demand depth shows a **broad plateau** (every scale >=1.5 beats N4) with a structural threshold (demand must exceed the 160 picks a draft consumes, scale >1.14). **Scales x2.5 and x3.0 pass EVERY gate** (+26.7/+28.2, CIs excluding zero, LOSO positive on all 5 seasons, 0 cap breaches, K 1.74->0.00 in late rounds). x2.5 generalizes out-of-format: +65.6 (CI [+31.8,+99.5]) on legacy_2qb_dynasty. Caveat: the passing scale was selected post-hoc from a 6-point sweep. Next: pre-register a scale on the structural criterion and run the official benchmark. |
| M15 User-facing productization | DONE | Real Sleeper league onboarding (`POST /league/register`, validated live before persisting), real roster import/bridging, My Team roster intelligence, Action Center (ranked ADD/DROP/TRADE), batch waiver ranking, Player Detail (universal vs. my-league value), Draft/Dashboard/multi-asset Trade-package views — all thin reads of already-tested M1-M13 tables/M10 functions, zero new decision logic. Found and fixed 6 real bugs by exercising the real app end to end with Playwright against a real Sleeper league (`boys_of_fall`), not by code review: 3 DuckDB/refetch concurrency bugs, a Sleeper snapshot-filename collision, a non-atomic-write torn-read race (reproduced directly: 5,292 torn reads/~2,000 concurrent reads with the old pattern, 0 with the fix), and a UI unmount-before-paint bug. See D53. 350 offline tests passing (up from 303); lint + `tsc --noEmit` clean. |
| M31 Pre-real-draft product gaps | DONE (2/3 shipped, 1 audited and stopped) | D72. Three product-correctness gaps closed before real-draft use, zero strategy/model change. **Sleeper draft-pick sync**: `league/sleeper_draft.py` + `GET /league/{id}/sleeper-draft` reconstruct the live board (drafted picks, whose turn, next pick) from Sleeper's own `draft/{id}/picks` feed; `DraftView.tsx` polls it every 8s and auto-recommends on the user's turn; manual entry kept only for non-Sleeper leagues. **League scoring audit**: roster/lineup config was already fully wired Sleeper->engine (no change needed); scoring VALUE (PPR/half-PPR) is NOT wired -- every projection is fixed full-PPR from nflverse, baked in at M3 -- correctly identified as a hard stop (re-deriving points per league would mean re-projecting the model stack) and NOT faked; a disclosure banner surfaces the mismatch instead. **Draft-state persistence**: `localStorage` keyed by `{sleeper\|manual}:{league_id}`, Sleeper's own completed picks never cached (always re-fetched live). Two real bugs found by live Playwright testing (not code review) and fixed: a `RuntimeError`-catching `_league_or_404` was reporting a transient Sleeper outage as 404 "unknown league" instead of 503; a load/save-effect race (reproducible under React StrictMode) clobbered just-restored persisted state with pre-load defaults on every reload, fixed with a `hydrated` gate. 12 new unit + 5 new API tests (851 offline total) + 2 new live-network tests against the real `dilworth`/`boys_of_fall` leagues; lint/build clean both sides. Full detail: D72. |
| M32 Production-readiness hardening pass | DONE | D73. Audited the full live-draft path (Sleeper -> roster/league context -> draft state -> recommendation -> UI) for a real upcoming draft; zero scoring/methodology change. Found and fixed a real load-bearing bug: mid-draft roster resolution read only `GET /league/{id}/rosters`, whose live-draft update behavior Sleeper's own docs do not document, risking marginal-starter-value pricing against a roster missing this team's own just-drafted players -- fixed by unioning in the authoritative `GET /league/{id}/sleeper-draft` picks feed (`api/routers/league.py::_augment_with_live_draft_picks`). Found and fixed a real unhandled-exception bug: a genuine Sleeper 429/5xx or malformed response bypassed every `except SourceError` handler and would 500 instead of degrading to 503 (`sources/sleeper.py`). Exposed a `DraftDecisionTrace` (runner-up, score gap, full scored candidate list, draft-state inputs) via `DecisionResponse.trace` and `decisions.provenance_json` -- Phase 4/5's "what is calculated but discarded before reaching the UI," now retained, with no change to what gets recommended -- the structured seam a future Claude strategic layer will read. Fixed two real `DraftView.tsx` bugs: an auto-recommend transition ref that didn't reset on league/roster switch, and a race letting a recommendation request fire before the first Sleeper draft-state sync resolved; added a stale-recommendation banner keyed off live pick count. Verified live against the real `dilworth`/`boys_of_fall` leagues (real team/roster fetch, real 180- and 40-pick completed-draft reconstruction, graceful 404/422 on bad input) -- no in-progress draft was available in either, documented as a limitation rather than faked. No autonomous Sleeper pick submission exists anywhere in the codebase (verified by repo-wide grep) -- the recommendation/action safety boundary is currently satisfied only because the action side does not exist yet. 866 offline tests passing (up from 853); lint/typecheck/build clean both sides. Full detail: D73. |
| M33 Claude strategic decision layer (Stage 1) | DONE | D74. New `strategy/` package sits above `league/draft.py`, never inside it -- zero changes to `league/`, `models/`, `features/`, `evaluation/`. `strategy/contracts.py` defines the typed boundary: `ClaudeDecisionContext` (built entirely from D73's already-computed `DraftDecisionTrace` plus `roster_need`, nothing independently fetched) and `ClaudeDraftDecision` (a schema-constrained FOLLOW_ALPHA/OVERRIDE_ALPHA response, pydantic-validated with an override-requires-a-reason self-consistency rule). `strategy/provider.py` calls the real `anthropic` SDK with a JSON-schema-constrained structured output, translating every real SDK error into a `ClaudeUnavailableError`/`ClaudeInvalidResponseError` pair mirroring `sources/base.py`'s existing error taxonomy; `FakeClaudeProvider` is what every test uses instead. `strategy/review.py` hard-validates Claude's selection against the exact candidate pool it was shown (never the full board) and self-consistency between decision/selected_player_id, persisting every outcome -- valid or rejected -- to a new `claude_decisions` table for replay, and falls back to Alpha's own (unaffected, already-computed) recommendation on ANY failure. New `POST /league/{id}/draft/claude-review` reuses the identical Alpha-computation helper `POST /draft` itself now calls (`_recommend_draft_pick_for_request`, extracted by refactor -- `POST /draft`'s own behavior confirmed unchanged) so there is exactly one recommendation engine, never two. `DraftView.tsx` adds a separate, opt-in "Get Claude's strategic review" button (never automatic per pick, for live-draft cost/latency discipline) showing agree/override/confidence/reasons/risk-flags and a staleness banner reusing D73's exact pick-count mechanism. No autonomous action: nothing in this package calls Sleeper or writes draft state; every path ends at a recommendation returned to the user. Real Anthropic API smoke test NOT performed -- no credentials available in this sandbox (verified), documented rather than faked; every other layer verified against a mocked SDK client or `FakeClaudeProvider`. 906 offline tests passing (up from 866: 31 + 9 new); lint/typecheck/build clean both sides. Full detail: D74. |
| M34 Final pre-draft verification | DONE | D75. Re-verified D73/D74 end to end from the code (not from memory) ahead of a real draft. Found and fixed one real bug: `<DraftView>` is not remounted on a Sleeper league switch, and `draftSync`/`decision`/`claudeReview` were never cleared on `leagueId`/`rosterId` change -- switching leagues could show a stale, wrong-league Alpha/Claude recommendation with no staleness warning (two leagues' pick counts can coincidentally match). Fixed with one reset `useEffect`. Verified with real evidence: mocked-Claude cases A-E all confirmed, including a new stale-decision-vs-changed-board test (Case D) that actually re-validates an old decision against a new context rather than only checking fingerprints differ; a new cross-league isolation test confirming `claude_decisions` rows never collide; a real `/draft/claude-review` call against the real `dilworth` Sleeper league with a real rostered player (Sleeper id `11581`) correctly priced as already-owned, the real live-picks feed executing cleanly, and Claude correctly reporting `claude_unavailable`; a full security grep (zero Anthropic references in `web/src`, no logging of credentials, zero write calls to Sleeper anywhere); and a re-measured payload (5 candidates regardless of a 150-player pool, ~1,220 tokens). Real Anthropic credentials remain unavailable in this sandbox -- unchanged from D74, still documented rather than faked. 908 offline tests passing (up from 906: 2 new); lint/typecheck/build clean both sides. Full detail: D75. |
| M35 Projection-compression investigation (D78) | DONE — Y1 shipped | D78. Answered a pre-draft report that the 2026 projections were materially miscalibrated at RB. **The reported symptom is mostly correct behaviour**: `E[max Y] > max E[Y]`, and against the model's own out-of-sample residual distribution the observed number of players beating the top projection is inside its 90% predictive band in **18 of 20** position-seasons (2025 RB: 11 observed vs 13.0 expected, band [9,17] — the model expected MORE than happened). The only real outlier in the window is 2024 RB. The cross-positional part is real (RB−WR top-decile gap +98.8 in 2024, +123.3 in 2025) but is a TREND, not a stationary bias, and **the FantasyPros consensus makes the identical error** — RB top-decile bias +38.96 for the market vs +39.21 for M6 over 2022-2025, a 0.25-point difference. Naively lifting the top of the board is measurably worse: the un-shrunk prior-season total reaches the highest top-of-board values of anything tested and is the worst projection in the comparison (MAE 49.4 vs 45.3). Nine candidate model changes measured walk-forward and rejected (RMSE loss +2.29 MAE, Huber +0.61, more capacity +2.81, Ridge +3.92, ppg×games +0.69, recency weights +0.16/+0.31, dropping ECR +1.83). **What did hold up were two defects in M6's TRAINING SPECIFICATION**, both position-agnostic and neither a calibration: the ECR sentinel 999 doubling as 'this season had no board at all' (2016-2019, ~44% of the RB rows behind a 2026 projection), and the point model never seeing season S-1 because it is spent entirely on conformal calibration. Pre-registered four arms and seven gates in git (`d976622`) before the confirmatory run; **Y1 shipped** by the pre-registered rule, Y2 FAILED G6, and Y3 — which scores better on every metric and clears every gate — was NOT taken because the rule was fixed in advance and Y2 is the component it adds. *[D108 marker: D101 re-ran these arms and the Y3 row does NOT reproduce — on the current snapshot Y3 FAILS G6 at WR under both readings of the gate. Y1 still passes all seven, so the rule re-applied still re-selects Y1. Cause unresolved (code drift and nondeterminism ruled out; the pre-D78 database is gone). Any citation of "Y3 passes all seven gates" must be re-derived, not quoted.]* Real backtest 2021-2025: MAE 42.31→40.88, RMSE 59.09→57.09, Spearman 0.757→0.770, better in all 5 seasons and at all 4 positions; conformal coverage_10_90 0.7901→0.7971 against a 0.80 target with interval widths unchanged. 2026 board top-12 mean: RB 206.3→222.4, WR 253.1→242.0 — the RB−WR gap narrows 27 points from a change with **no positional term in it**. Also found and fixed a production-BLOCKING bug the projection work had nothing to do with: `make` ran `features` before `team-scores`, so the K/DST step joined an empty `team_week_points`, wrote **zero DST rows in every season**, and a league starting a DEF would have scored zero for that slot in silence. Shipped `make project-current-season` ending on a `train projection-status` gate that calls the application's own loader rather than trusting exit codes. #2 (pick numbers) and #3 (roster-position sync) shipped, plus three real UI bugs found by driving the app — including the Draft view sitting on season 2025 while 2026 projections existed. 927 python (961 offline incl. leakage/contract) + 15 frontend tests, and the live network suite re-run clean at 43 passed / 1 skipped / 0 failed (was 2 failed); a 20-step live draft rehearsal in real Chromium passed 20/20. The live suite also exposed two PRE-EXISTING failures, neither caused by D78: a stale 2QB-era assertion left by D58's retarget, and a real bug -- `evidence_score_for_action` fell back to a hardcoded September 1st Week-1 cutoff, so every preseason signal between 1 September and the real opener (the week most redraft leagues draft in) was silently discarded from EDGE; replaced with the league's own scheduling rule, which reproduces all eleven ingested Week 1 dates exactly. The Y1 draft-layer contrast is a NULL (-15.8, CI [-89.2, +57.6]); Y1's demonstrated benefit is projection accuracy only. A 20-step live draft rehearsal in real Chromium passed 20/20. Full account: `docs/DECISIONS.md` D78. |

## M1 summary
- Adapters: `nflverse` (15 datasets), `dynastyprocess` (4), `cfbfastr` (1), `ffopportunity` (1)
  — all AVAILABLE, verified against the live sources (both mocked-contract tests and
  `network`-marked live tests). `sleeper` (6 endpoints) verified BLOCKED_BY_POLICY at the time;
  `fantasypros` (2) and `cfbd` (3) verified NO_CREDENTIALS, and both provably never attempt a
  network call without a configured key (see `test_fantasypros_without_key_never_makes_network_call`
  / `test_cfbd_without_key_never_makes_network_call`).
  **Update (D31, 2026-08-22): the environment's network policy changed. `sleeper` is now
  genuinely AVAILABLE with real data; `fantasypros`/`cfbd` are now network-reachable too and
  blocked only on the still-missing API keys, not policy — see `docs/DATA_SOURCES.md`.**
  **Update (D36, 2026-08-23): `cfbd` moved from NO_CREDENTIALS to genuinely AVAILABLE — a real
  `CFBD_API_KEY` is live, verified with real data across all 3 datasets. `fantasypros` is not
  resolved the same way: a real `FANTASYPROS_API_KEY` is present and being sent, but FantasyPros's
  own API rejects it (`403 Forbidden`), so it stays blocked, now for a different, more specific
  reason than a missing key — see `docs/DATA_SOURCES.md`.**
  **Update (D37, 2026-08-23): `fantasypros` is now also genuinely AVAILABLE — the `403 Forbidden`
  was a wrong adapter base URL (missing `/public`), not a bad or unrotated key; fixed, both
  datasets confirmed live with real data — see `docs/DATA_SOURCES.md`.**
- `snapshot_registry` + `source_health_log` tables in DuckDB; every fetch writes an immutable
  file under `data/raw/<source>/<dataset>/captured_at=<date>/...` and is content-hashed.
- `alpha-squad sources status` and `alpha-squad sources ingest --season-start Y --season-end Y`
  both real, run against live sources. A multi-season smoke ingest (2023-2026) produced 46 real
  snapshots and correctly reported 8 NOT_FOUND for genuinely unpublished 2026 weekly/game-level
  datasets — nothing fabricated.
- Two real bugs found and fixed during self-review (not just written and assumed correct):
  1. `sources status` was writing real files to disk and reporting AVAILABLE without ever
     calling `record_snapshot`, so the registry silently stayed empty while the CLI reported
     success. Fixed by making status and ingest share the same fetch+record path; regression
     tests in `tests/unit/test_storage_snapshots.py`.
  2. `Settings` fields use `validation_alias` (so env vars match `.env.example`'s names) but
     without `populate_by_name=True`, pydantic silently dropped `Settings(data_dir=...)`-style
     kwargs and fell back to defaults, with `extra="ignore"` hiding the resulting
     ValidationError — meaning test fixtures believed they were isolated to `tmp_path` but
     were actually writing into the real repo `data/` directory. Fixed; regression tests in
     `tests/unit/test_settings.py`.

## M2 summary
- `players` (25,046 rows): spine anchored on nflverse `players.gsis_id` — verified 100%
  populated, unique. `player_id = 'asq_' || substr(md5(gsis_id), 1, 16)`, deterministic (not
  a persisted counter), so rebuilds are reproducible.
- `player_id_map` (25 id_types, ~180k rows total): normalized ID-to-ID crosswalk — 8 native
  nflverse IDs (gsis/pfr/espn/otc/esb/nfl/smart/pff) + 15 DynastyProcess IDs (mfl/sleeper/
  yahoo/ktc/etc.) + cfb_player_id (draft_picks) + cfb_id (combine). `(id_type, id_value)` is
  a hard PRIMARY KEY; `insert_id_mappings()` detects and quarantines collisions *before*
  writing rather than relying on the constraint to fail the whole build.
- `player_college_bridge`: 7,990 `cfb_player_id` + 6,131 `cfb_id` mappings, feeding rookie
  modeling (M7) directly from real draft_picks/combine data.
- `identity_exceptions`: 1,639 rows on first build (1,152 unmapped historical draft picks,
  389 unmapped combine prospects who never made a roster, 70 orphan DynastyProcess gsis_ids,
  28 genuinely self-inconsistent DynastyProcess rows) — quarantined, not dropped or guessed.
  Idempotent by design: re-running the build never reverts a human-resolved exception back
  to PENDING (regression-tested).
- Full build against live data: ~13 seconds, zero integrity violations (no duplicate keys,
  no orphaned foreign keys, no null gsis_id) — verified by both a live network test and
  direct inspection.
- Three real bugs found and fixed during self-review before considering this done:
  1. **Hash algorithm mismatch**: `mint_player_id()` (Python, for code needing an ID without
     a DB round-trip) used sha256 while the embedded SQL used md5 — would have minted two
     different IDs for the same gsis_id depending on code path. Fixed by extracting a single
     `PLAYER_ID_SQL_EXPR` constant both paths use; regression-tested for parity.
  2. **Severe performance bug**: `insert_id_mappings` and the college-bridge upsert looped
     over matched rows in Python, calling `con.execute()` once per row — profiled at 88
     seconds for 25,000 rows (~3.5ms/call overhead), which made a full identity build hang
     for minutes across ~25 id_types. Rewritten as set-based `INSERT...SELECT...RETURNING`
     (one round trip per id_type); full build now takes ~13s. `executemany()` was profiled
     too and found equally slow — the fix is genuinely set-based SQL, not a different batch
     API.
  3. **Wrong join target**: the draft_picks/combine college-bridge builders assumed a
     `players.pfr_id` column that doesn't exist — pfr_id (like every other native ID) lives
     in `player_id_map`, not denormalized onto `players`. Fixed to join through
     `player_id_map WHERE id_type='pfr_id'`.
- Real DynastyProcess data-quality issues discovered and handled (docs/DECISIONS.md D12/D13):
  the CSV export uses the literal string `"NA"` for missing values in every column including
  IDs (handled via `nullstr=['NA']`), and the export itself contains internally-inconsistent
  duplicate gsis_id rows (e.g. one gsis_id mapped to two different player names) — quarantined
  rather than trusting whichever row loaded first.

## M3 summary
- `games` (3,028 rows, 2015-2025): derived from `pbp`'s `game_id`/`game_date` since nflverse
  publishes no separate schedules dataset (verified 404) — the anchor for every as-of check.
- `player_week_stats` (199,632 rows): normalized `stats_player_week` + `snap_counts`,
  identity-joined once (gsis_id direct to spine; pfr_id through `player_id_map` for snaps,
  same pattern as the M2 college bridge).
- `player_week_features` (199,632 rows): the engineered lag/rolling panel — leakage-safe *by
  construction* via SQL window frames (`ROWS BETWEEN N PRECEDING AND 1 PRECEDING`), not by
  trusting a date filter. `target_fantasy_points_ppr` is the real unlagged outcome, kept only
  as the training target.
- `features_as_of(con, date)` is a second, independent row-level safety layer (`game_date <
  as_of`, strict) for reconstructing "what was known as of date D" — verified both offline
  and against real data that a game on the as-of date itself is correctly not yet visible.
- Leakage tests (tests/leakage/): poison/sentinel injection, target isolation via independent
  Python recomputation (not reusing the SQL under test), season-reset verification, and
  rebuild-invariance (appending future weeks and rebuilding must not change historical rows'
  stored features) — all passing, both offline (synthetic fixtures) and against real data.
- Full build against 11 real seasons (2015-2025) of cached data: ~7 seconds.

## M4 summary
- `player_season_stats` (21,421 rows): season aggregate of M3's `player_week_stats`.
- `market_snapshot` (210,730 rows): normalized DynastyProcess `fp_ecr_history` ('ro'
  redraft-overall series), identity-joined via `fantasypros_id` (verified 93.8% coverage —
  D16). Extended in M8 with the 2QB-aware series the target league (D7) actually needs.
- Three baselines, all walk-forward (season S predictions read only data from before S):
  `baseline_previous_year`, `baseline_weighted_2yr` (0.65/0.35), `baseline_ecr_implied`
  (isotonic rank-to-points calibration curve, fit per position on an expanding window of
  prior seasons only — D17). "ADP-implied" is LIMITED to this same ECR-based substitute; no
  independent ADP series is reachable (D16).
- Shared evaluation harness (`models/evaluate.py`): MAE, RMSE, R², Spearman, top-12/24 hit
  rate, tier accuracy — computed overall and per position, persisted to `evaluation_results`,
  published to `reports/baseline_evaluation.md`. Every later model (M5, M7, M8) reports
  through the same harness so comparisons are apples-to-apples, per ACCEPTANCE_CRITERIA.md.
- **Correction (superseded by the M5 fix below):** an earlier version of this section claimed
  the ECR-implied baseline's MAE was "substantially worse" than the simple historical
  baselines' based on comparing ecr_implied's correctly-scoped MAE (~45-49) against the other
  two baselines' *unscoped* "ALL positions" MAE (~14-15). That comparison was invalid — see
  docs/DECISIONS.md D19. With the fix, all three baselines land in the same ~45-53 MAE range
  for "ALL" (QB/RB/WR/TE only), a much more sensible result.

## M5 summary
- `team_week_stats`/`team_week_features` (6,056 rows): team-environment signal (plays, pass
  rate, EPA) from `stats_team_week`, leakage-safe by construction (same window-frame pattern
  as M3), attached onto `player_week_features` by (team, season, week).
- **Weekly/in-season models** (`models/established/train.py`): Ridge, CatBoost, XGBoost,
  plus standalone opportunity-only and team-environment-only models (isolating each signal's
  own predictive power — team-environment alone is markedly the weakest, MAE 30-56 vs 10-19
  for the full models, exactly as expected: team context alone barely predicts individual
  output), and an ensemble that's only marked `validated=True` in `model_registry` when it
  beats every component model's MAE out of sample that season (ARCHITECTURE.md §5/§12).
  Trains on seasons < S, predicts every week of season S using that week's already-lagged
  features, aggregates to a season total for comparison. Real result: Spearman 0.94-0.98,
  MAE 10-19 for the full models — strong, because this task has access to season S's own
  in-progress weeks (a genuinely different, easier task than preseason projection).
- **Season-level/preseason models** (`models/established/season_level.py`): Ridge, CatBoost,
  XGBoost trained on season S-1 aggregate + preseason ECR rank only — the actual
  apples-to-apples comparison against M4's baselines, since both use only pre-S information.
  Real, modest, genuine result: e.g. WR 2024, `ml_season_catboost` MAE 44.27 vs the best M4
  baseline (`ecr_implied`) at 45.05 — CatBoost edges out every baseline slightly, without
  overclaiming a dramatic win. Documented per-position, not hidden either way.
- Two model families, not one, precisely because comparing the weekly model against M4
  baselines would have overstated ML's advantage (different information sets) — see D18.
- **Real bug found and fixed during this milestone's review**: `models/evaluate.py`'s "ALL
  positions" rollup pooled *every* position in `player_season_stats` (LB, CB, K, P, etc. —
  ~900 of 1,512 rows for 2024), most of which correctly score ~0 PPR points. Their
  near-perfectly-predictable near-zero outcomes diluted the pooled MAE to ~14.7, while every
  individual skill position's real MAE was 33-65 — a materially misleading number that had
  been silently wrong since M4. Fixed with `SKILL_POSITIONS = ("QB","RB","WR","TE")` scoping
  the "ALL" rollup; per-position numbers were never affected (D19). All M4 and M5 evaluation
  reports were regenerated after the fix; regression-tested.

## M6 summary
- `uncertainty_predictions`: p10/p25/median/p75/p90 + top12_prob/top24_prob + a documented
  confidence heuristic, one row per (player, season, model_version) — field names mirror
  AGENT_CONTRACTS.md's Prediction contract directly.
- Split-conformal method (`models/uncertainty/conformal.py`): signed calibration-residual
  quantiles (not a symmetric margin), so intervals can be asymmetric — verified this matters
  with a synthetic right-skewed-residual test (p90 offset larger in magnitude than p10).
  Three-way, strictly time-ordered split per target season S: proper-train (< S-1) ->
  calibration (S-1 only, held out from training) -> target (S). Top-12/24 probabilities via
  Monte Carlo: resample from the empirical calibration-residual distribution 2,000x per
  player, rank within the simulated draw, measure how often each player lands in the top
  12/24 among their position peers.
- `calibration_diagnostics`: out-of-sample empirical coverage, published to
  `reports/calibration_report.md`. Real result on 2019-2025 QB/RB/WR/TE: coverage_10_90
  mostly 0.72-0.90 against a target of 0.80 (one outlier at 0.69, WR 2024) —
  genuinely close to nominal, not just directionally plausible. This is the "measure
  calibration" / "do not present false precision" requirement actually verified against real
  data, not asserted.
- 3,120 real predictions written on the full 2019-2025 run.

## M7 summary
- `combine_results` (7,031 rows): athletic testing bridged via `pfr_id` through
  `player_id_map`, same pattern as M3's snap counts.
- `rookie_features` (1,077 real rookie-seasons, 2016-2025 shown at ~90-103/class): draft
  capital (direct from `players`), combine testing, and landing spot (drafting team's
  *prior*-season pass rate/plays — never the rookie's own season, to avoid a look-ahead).
  breakout_top24 derived from actual within-position season rank, not a hardcoded points
  threshold.
- College production is LIMITED: cfbfastR-data's college identifiers are numeric ESPN-style
  IDs with no verified bridge to the nflverse-derived identity graph, and its "player_stats"
  dataset is raw play-by-play, not aggregated season totals — building both a fuzzy-match
  bridge and touchdown-attribution aggregation was judged a materially larger undertaking
  than this milestone's budget justified, especially since draft capital already
  substantially proxies for it (D20). Not fabricated via a shaky join; documented as a real
  gap with a defensible fallback.
  **Update (D38, 2026-08-23): the identity bridge exists after all — CFBD's own numeric athlete
  IDs are the same ID as `espn_id`, verified against real players with zero fuzzy matching.
  `college_usage` (season usage share, via CFBD) is joined into `rookie_features` for each
  rookie's final college season only, leakage-safe.**
  **Update (D39, same day): the feature was then actually measured, and rejected.** Over
  identical walk-forward folds the college features were neutral-to-slightly-worse on every
  metric that matters (breakout Brier +0.0030 vs baseline; worse on all four metrics when
  restricted to draft classes with ≥83% coverage). `FEATURES` reverts to the 12-feature D20
  baseline and `FEATURE_VERSION` to `rookie_features_v1`. The data pipeline, the bridge and the
  ablation harness are all kept — the experiment re-runs with
  `alpha-squad train rookie --ablation`. So college production remains LIMITED, but now for a
  measured reason rather than a missing-source one. See D39.
- CatBoostRegressor (rookie-year PPR points) + CatBoostClassifier (top-24 breakout,
  Brier-scored) walk-forward strictly by draft class (train on classes < C, predict C).
  Real results: regression Spearman mostly 0.4-0.8 (rookie prediction is inherently noisier
  than established-player prediction — no prior NFL data exists), breakout Brier scores
  mostly 0.02-0.12 against base rates of 2-27%.
- Historical comps (nearest-neighbor on standardized draft capital + combine, never drawing
  from the target's own or a later class): spot-checked against real 2023 RB rookies —
  Jahmyr Gibbs' and Bijan Robinson's top comps were plausible past first-round backs
  (Ezekiel Elliott, Clyde Edwards-Helaire).
- Two real bugs found and fixed during this milestone's review:
  1. Combine's `ht` column is a feet-inches string (`"6-0"`), not a number — a direct
     `CAST(... AS DOUBLE)` failed outright. Fixed by parsing `split_part` into inches.
  2. The comps nearest-neighbor crashed with a dtype error (`'float' object has no
     attribute 'sqrt'`) because the query-target row's integer columns came back as pandas
     nullable Int64 (bypassing `load_rookie_class_data`'s imputation), producing an
     object-dtype array `np.linalg.norm` couldn't handle. Fixed with an explicit
     `.astype(float)` after concatenation.

## M8 summary
- `market_snapshot` extended from `ecr_type='ro'` only (M4) to `ro`/`do`/`rsf`/`dsf`
  (682,397 rows total, 3,112/1,994/1,390/1,189 distinct players respectively). `rsf`
  (redraft-superflex, 2QB) is the series EDGE uses — it is a genuinely different market than
  `ro`: real data shows QBs occupying most of the top overall `rsf` slots, exactly what a 2QB
  league should produce and `ro` does not (D21).
- `dynasty_values` (681 rows, 97.6% real fantasypros_id coverage): normalized from
  DynastyProcess's `values-players.csv`, current 1QB/2QB dynasty ECR and value — reserved for
  M10's dynasty trade logic, not consumed by M8's single-season EDGE (D21 explains why mixing
  horizons would be wrong).
- EDGE (`edge_snapshot`, `AGENT_CONTRACTS.md`'s Edge contract): compares the M6 uncertainty
  model's single-season point/top24 predictions against `rsf`'s overall (cross-position) rank,
  both horizon-matched. `model_rank`/`market_rank` are cross-position; `projected_points_edge`
  comes from a pooled walk-forward isotonic rank→points curve; `probability_edge` from a
  per-position walk-forward isotonic rank→top24 curve (re-deriving a within-position rank from
  the overall `rsf` order, since the series carries no explicit position rank).
- Hard gating rule (D21, `classify_action` in `market/edge.py`): BUY/SELL requires rank edge
  AND points edge to agree in direction AND both clear a materiality threshold (rank ≥ 15,
  points ≥ 15 PPR) AND model confidence ≥ 0.5. A rank gap alone, or a rank/points disagreement,
  or low confidence, is never more than WATCH — literally regression-tested in
  `tests/unit/test_edge.py::TestClassifyActionGatingRule`, and re-verified against real stored
  output in the live test.
- Historical EDGE validation (`edge_validation_results`, real data, `rsf`, 2022-2025 — 2021 is
  WATCH-only since `rsf` history itself only starts in 2021, leaving no walk-forward training
  season): **as of M13** (see D28 — these figures were recomputed after a postseason-game
  contamination bug in the underlying weekly stats was found and fixed, and differ from the
  M8-era numbers originally reported here) — the **BUY cohort beat market-implied points in 3
  of the 4 scored seasons** (+19.77, +15.07, +13.98 PPR in 2022-2024; essentially flat at
  -0.56 PPR in 2025; n=31-47/season), a genuine, real, out-of-sample signal that the gated EDGE
  finds real market inefficiency in most seasons, not noise, though not a guarantee every
  season. The **SELL cohort moved the same direction as the market's real mistake in 3 of 4
  seasons** (-47.00/-21.92/-18.32 PPR in 2022-2024; wrong direction in 2025 at +36.91 PPR,
  small n=8-21/season) — reported honestly per CLAUDE.md, not suppressed.
  Real example: Tyler Higbee 2024 (`model_rank`=141 TE, `market_rank`=258 overall,
  `rank_edge`=+117, `points_edge`=+52.6, BUY) — matches a well-documented real dynasty-market
  pattern where 2QB/superflex ADP over-drafts QBs and pushes TE value down the board.
  (The M8-era version of this paragraph used Travis Kelce 2024 as the illustrative example;
  his real corrected 2024 season total dropped enough after the D28 fix — his 3 real 2024
  playoff/Super Bowl games, previously double-counted into his "season" total, are real games
  but not part of a regular-season projection — that his own EDGE call flipped from BUY to
  SELL. Left in as a concrete illustration of the bug's real impact rather than quietly
  swapped out.)
- `evidence_score` is a disclosed neutral placeholder (0.5) pending M9 — reported in every
  `edge_snapshot` row and its `reasons` for transparency, but never used to gate BUY/SELL/HOLD/
  WATCH (D21). This is not a corner cut silently: the field exists with the exact contract
  shape now, and M9 only needs to start producing a real score into the same column.

## M9 summary
- `evidence_events` (real data, 2019-2025: **33,311 events** — 8,231 usage_share_spike,
  7,720 usage_share_drop, 8,200 injury_own_status, 2,539 injury_teammate_opportunity, 2,397
  depth_chart_promotion, 2,000 depth_chart_demotion, 2,006 roster_transaction): four Strong-tier
  detectors (`evidence/events.py`), all on officially-sourced nflverse structured data, every
  event dated strictly before the week it informs (leakage-safe by construction, same
  discipline as `features/panel.py`). PRODUCT_SPEC.md's full Strong/Medium/Weak taxonomy is
  registered in `evidence/taxonomy.py`; Medium/Weak have no detector (no reachable news/social
  source, D5) but share the same `record_event()` contract for future manual entry (D22).
- Real, spot-checked example matching an actual documented 2024 event: Amari Cooper's week-8
  2024 evidence-adjusted projection (10.27 -> 8.88, -13.5%) is driven by `roster_transaction`
  (Cleveland -> Buffalo, the real in-season trade) plus `usage_share_drop` (snap_pct 0.35 vs.
  his own 0.86 trailing average) — the detectors independently reconstructed a real, verifiable
  storyline from structured data alone, not fabricated.
- `weekly_projection_snapshot`: M5's `train.py` was already computing a real per-week point
  prediction (`ml_catboost`) internally and discarding it after season-aggregation; this
  milestone persists it (12,212 real rows for a 2023-2024 smoke run) since evidence is
  inherently a weekly signal, not an annual one.
- `projection_deltas` (`evidence/prior_update.py`): bounded (±15% of the base value, hard
  cap `MAX_ADJUSTMENT_PCT`) adjustment from aggregated same-week evidence, applied to
  `weekly_projection_snapshot` and written to a **separate** table — the base row is only ever
  read, never mutated (regression-tested against both synthetic data and this milestone's real
  12,212-row run: `tests/unit/test_evidence.py::test_never_mutates_the_base_weekly_projection_row`,
  `tests/integration/test_evidence_live.py::test_evidence_never_overwrites_the_real_weekly_projection`).
  Every material delta carries a human-readable `reason` and its source `evidence_ids`.
- M8's EDGE `evidence_score` is now real (`evidence_score_for_action`), not the D21 placeholder:
  computed from `evidence_events`, defaulting to neutral 0.5 when none exist. In practice it
  stays neutral for M8's preseason-anchored EDGE (real detectors only ever produce in-season
  events, and EDGE compares preseason market snapshots) — an honestly-reported horizon mismatch,
  not a disguised placeholder (D23). `classify_action` now vetoes an otherwise-valid BUY/SELL to
  WATCH only when evidence *actively contradicts* the action (`evidence_score < 0.35`); neutral
  evidence never blocks. M8's already-published historical BUY/SELL numbers are unchanged by
  this wiring (every one of those calls saw neutral evidence, which trivially clears the veto).
- Real bug found and fixed during this milestone's review (D24): nflverse's `depth_charts`
  release has two incompatible real historical schemas (pre-2025: `week`-keyed with
  `depth_team`/`depth_position`/`club_code`; 2025+: near-daily `dt`-keyed with
  `pos_rank`/`pos_abb`/`team`). The initial implementation assumed the new schema everywhere
  and crashed outright (`BinderException: column "dt" not found`) on every pre-2025 season.
  Fixed with schema detection in `evidence/events.py::_depth_chart_entering`, normalizing both
  into the same shape before any diff logic runs.

## M10 summary
- `league/context.py`: `LeagueContext` mirrors AGENT_CONTRACTS.md's League context contract
  exactly (`extra="allow"` + free-form dicts for lineup/scoring/roster/etc., so arbitrary
  league settings can be represented per ACCEPTANCE_CRITERIA.md), loaded from
  `config/league_configs/target_league.yaml` (10 teams, 2QB/2RB/2WR/1TE/2FLEX, dynasty PPR,
  bench 10, FAAB $100 — D7's defaults).
- `league/replacement.py`: real value-based-drafting (VBD) with flex allocation — dedicated
  slots filled first by within-position rank, then flex slots earned by the single best
  remaining players across every flex-eligible position (not split evenly). Verified against
  real 2025 uncertainty_predictions (455 real players): exactly 20 dedicated QB starters (10
  teams x 2, matching the target league precisely) and a QB replacement level (~220 pts) far
  above RB/WR/TE's (~138-146 pts) — the target league's 2QB format genuinely reshapes the
  market, not a hardcoded assumption. Real, disclosed finding worth a future look: at this
  model's real rank ~18-26, WR point_prediction values exceed RB/TE's enough that every FLEX
  slot in this run went to WR — a legitimate downstream consequence of M5/M6's own
  already-validated (by those milestones' own gates) predictions, not a bug in M10's
  allocation logic, but a candidate for cross-position calibration review in a future model
  refinement pass.
- Real coverage gap found and fixed: M6's uncertainty model structurally excludes true
  rookies (0/442 real 2024 rows). `load_season_projections` now fills any player missing from
  `uncertainty_predictions` in from M7's real `rookie_predictions`, so waiver/draft tools can
  evaluate rookies at all (D25).
- `league/draft.py`: VORP x roster-fit x model-confidence x next-pick-survival-probability
  scoring, with alternatives and reasons (Decision contract). Survival probability models the
  real `ecr_best`/`ecr_worst` expert-rank dispersion (M4/M8) as Uniform(best, worst) — real
  data, not a fabricated distribution.
- `league/waiver.py`: meaningful-role probability (M6 top24_prob), dynasty value (M8), a
  value-spike read from real recent M9 evidence, roster fit, replacement level, a
  scarcity-and-role-based competing-bid-likelihood heuristic, and a bounded (≤40% of budget)
  FAAB bid. Real, spot-checked example: Keon Coleman (2024 rookie WR), whose static
  preseason-anchored projection is *below* WR replacement level (a realistic outcome for many
  rookies), still gets a real, non-zero recommended bid ($18.94 of $100) because his real,
  detected `depth_chart_promotion`/`usage_share_spike` evidence (his actual real-life
  promotion to WR1) drives the value-spike term — verified this would have incorrectly zeroed
  out under a naive marginal-value-only formula, and fixed (D25).
- `league/trade.py`: dynasty buy/hold/sell/watch built directly on M8's real, already-validated
  EDGE action/reasons and DynastyProcess's real `value_2qb`, with a clearly-labeled,
  documented age-curve heuristic (NOT a trained model — no ground-truth dynasty-decay dataset
  exists to fit one, D25) as a disclosed secondary adjustment only.
- `decisions` table (AGENT_CONTRACTS.md's Decision contract): every `league draft`/`waiver`/
  `trade` CLI call persists its recommendation, alternatives, expected value, confidence,
  reasons, and provenance — the pure recommendation functions themselves stay side-effect-free
  and unit-tested independently.
- 29 new offline unit tests (152 total), covering the VBD algorithm's flex-earned-not-split
  behavior, the literal 2QB-vs-1QB replacement-level difference, survival-probability edge
  cases, roster-need bounds, and the evidence-driven bid override case. 5 new live network
  tests (`tests/integration/test_league_live.py`, 26 total network) validate the same logic
  end-to-end against real 2022-2025 data, including confirming the M7 rookie-prediction
  fallback actually returns a usable projection for a real rookie-only player.

## M11 summary
- `agents/contracts.py`: pydantic `Task`/`Result`/`EvidenceContract`/`PredictionContract`/
  `EdgeContract`/`DecisionContract` mirror AGENT_CONTRACTS.md's JSON examples field-for-field
  (`extra="allow"` throughout). League context is *not* redefined here — it reuses M10's real
  `league.context.LeagueContext`, a single source of truth.
- `agents/registry.py`: 9 real agents (`data_engineering`, `player_identity`, `projection_ml`,
  `rookie_ml`, `market_edge`, `news_evidence`, `fantasy_strategy`, `evaluation_qa`,
  `research_validation`) — every one a thin, deterministic wrapper around the exact M1-M10
  functions already built and validated in their own milestones (D14/D26). `research_validation`
  (optional per AGENT_CONTRACTS.md) honestly reports NEEDS_REVIEW rather than fabricating a
  finding: no unstructured research capability is reachable in this environment.
- `agents/orchestrator.py`: real DAG scheduling (topological readiness, not a fixed order),
  retry/backoff (2 retries, verified recovering a real transient-failure stub), and genuinely
  concurrent dispatch of independent tasks — verified two real stub tasks start within 0.2s of
  each other, not sequentially. `agent_tasks`/`agent_results` persist every state transition;
  `reconstruct_run` rebuilds a full run's status purely from that DB state, satisfying
  IMPLEMENTATION_PLAN.md's M11 gate directly (regression-tested, and re-verified against a
  real orchestrated run of `data_engineering` -> `player_identity` against live nflverse data).
- Real concurrency bug found and fixed via the orchestrator's own test suite (D26): running
  `init_db()` (which includes `ALTER TABLE`) from multiple worker threads' own connections hit
  a real DuckDB `Catalog write-write conflict` under genuine concurrent dispatch. Fixed by
  running schema DDL exactly once, before any worker thread opens a connection.
- `agents/disagreement.py`: reuses M8's real `edge_snapshot.rank_edge` (model-vs-market) and
  M4/M5's real `evaluation_results.mae` (baseline-vs-ML) rather than deriving new comparisons.
  Verified against real 2024/2025 data: 292 real model-vs-market rank disagreements and 4 real
  baseline-vs-ML disagreements (established-ML beats the ECR baseline's MAE by roughly 3x at
  every position, consistent with M5's own published numbers) were detected, resolved, and
  recorded with both positions preserved (never silently discarding the minority, per
  AGENT_CONTRACTS.md's conflict protocol).
- `evaluation_qa`'s REJECT capability reuses M5's own real `model_registry.validated` gate
  (ACCEPTANCE_CRITERIA.md: "Evaluation/QA can reject unsupported claims") rather than inventing
  a new judgment.
- `milestones` table + `record_milestone`: milestone state (ACCEPTANCE_CRITERIA.md: "Milestone
  state is persistent") is written at the start and end of every orchestrated run, independent
  of any individual task's state.
- 20 new offline unit tests (172 total) plus 3 new live network tests (29 total), including a
  real orchestrated run against live nflverse/DynastyProcess data and real disagreement
  detection against a full real season's established-ML/baseline/EDGE results.

## M12 summary
- `src/alpha_squad/api/`: FastAPI app with 8 routers (`players`, `rankings`, `rookies`,
  `edge`, `evidence`, `league`, `provenance`, `health`). Every response field is a direct
  projection of an already-persisted table (`uncertainty_predictions` M6, `rookie_predictions`
  M7, `edge_snapshot` M8/M9, `evidence_events` M9, `source_health_log` M1) or a direct call
  into the exact M10 function the CLI calls (`recommend_draft_pick`, `recommend_waiver_pickup`,
  `recommend_dynasty_trade`) — D27 documents why there is no parallel logic path anywhere in
  this package. `/provenance/{id}` traces any ID across every table that could own it. A
  missing/unknown league returns 404, never a fabricated universal answer.
- `web/`: a real React + Vite + TS SPA (six views: Rankings, EDGE, Rookies, Evidence, League,
  Source Health), deliberately lean rather than polished (PRODUCT_SPEC.md frames the SPA as
  presentation-only) but genuinely live — every view fetches the real API, no mock data, no
  client-side scoring/ranking. BLOCKED_BY_POLICY/NO_CREDENTIALS source badges render honestly
  (verified: cfbd/fantasypros show amber NO_CREDENTIALS badges with the real reason text, not
  hidden behind a generic status).
- Verified end-to-end in a real Chromium browser (Playwright, the environment's pre-installed
  browser — CLAUDE.md's "start the dev server and use the feature in a browser" requirement):
  all six views loaded and rendered real persisted data (real players — Lamar Jackson/Josh
  Allen top QB rankings, Tyler Conklin/real TE BUY signals on EDGE, Ashton Jeanty atop 2025
  rookies, a real Storm Duck injury event); the League tab's draft form was submitted and
  returned the same recommendation/reasons the CLI produces for identical inputs; and the
  literal Gate 8 test was performed, not just written: the API process was killed and the page
  reloaded, producing a real fetch error in the UI rather than stale or fabricated content. A
  real UX bug (the error message literally said "as intended," written for this decision log
  rather than a user) was caught during that same review pass and fixed.
- Real gap found and fixed during review (D27): `RankingRow` initially omitted `prediction_id`,
  which would have made a ranking untraceable through `/provenance` — added, along with a live
  test proving the trace actually resolves to the real source row.
- 17 new offline API tests (189 total) using FastAPI's `TestClient` with `get_db` overridden to
  an in-memory DB — including a literal test that `/rankings`/`/edge` return the *exact* stored
  values from a seeded row, proving no re-ranking/re-scoring happens in the API layer. 4 new
  live network tests (33 total) exercise the same endpoints against a real, live-ingested
  dataset.

## M13 summary
- **Correlated team-season Monte Carlo simulation** (`models/simulation/`), the item deferred
  since D8: `team_scores.py` derives real final team scores per (team, season, week) from
  `pbp`'s running score columns; `correlated.py` samples one joint (plays, pass_rate,
  team_points) draw per simulated trial from a team's real historical covariance, and derives
  every rostered player's simulated weekly points from that *same* trial's draw via their real
  opportunity share and efficiency — the shared-randomness structure genuine QB/WR1 correlation
  requires, measured empirically rather than assumed. Wired into the CLI
  (`alpha-squad simulate team-season`), persisting a summary row to `team_simulation_runs`.
  Verified across all 32 real NFL teams x 3 seasons (2022-2024, 96 simulations):
  `qb_wr1_correlation` positive in 100% of runs (mean 0.358, range 0.27-0.46).
- **A real, cross-cutting data bug found and fixed (D28), not scoped to M13's own new code.**
  Building the simulation surfaced that `player_week_stats`/`team_week_stats` (M3) had silently
  included postseason NFL games in every "season" aggregate since the very first ingestion —
  nflverse's weekly releases carry postseason weeks with no flag of their own, and the REG/POST
  distinction that `games` already tracked (`game_type`) was never joined against when building
  those two tables. This inflated `player_season_stats` (feeds M4's baselines), let a team's
  trailing "last 3 games" feature silently pull in a playoff game, and inflated the season
  totals used everywhere else — for every playoff team's players, in every one of the 11
  ingested seasons (2015-2025), not just M13. Fixed at the source (an explicit
  `game_type = 'REG'` join condition); the already-populated tables needed an explicit `DELETE`
  (8,543 stale rows from `player_week_stats`, 266 from `team_week_stats` — an upsert alone
  cannot remove keys a corrected query stops producing). Every downstream step was re-run
  against the cleaned tables: `features build`, `evaluate baselines`, `train established`,
  `train established-season`, `train uncertainty`, `train rookie`, `edge build`, `edge
  validate` — all from already-cached local snapshots, no new network fetch needed. The
  qualitative findings are unchanged (ML still beats baselines by a wide margin at every
  position; EDGE's BUY cohort still beats market expectation in most seasons) but the exact
  numbers shifted, most visibly EDGE's real Travis Kelce 2024 example flipping from BUY to SELL
  once his 3 real playoff/Super Bowl games stopped being double-counted into his "season" total
  (see the corrected M8 summary above). A regression test
  (`tests/unit/test_features.py`) asserts a synthetic postseason game's stats never reach either
  table.
- **Two further simulation-design bugs, both caught by checking real numbers against known
  real outcomes rather than trusting that the code ran without error (D29):** (1) the QB's
  simulated output was anchored to `team_points` rather than `pass_attempts` — both come from
  the same per-trial draw, but real per-team history shows `pass_attempts` and `team_points`
  are only weakly (sometimes negatively) related, due to ordinary game-script effects, so the
  QB rarely landed in the same "big passing game" trial as his own WR1; `qb_wr1_correlation`
  measured -0.03 before the fix. Re-anchored the QB to `pass_attempts * (real points per pass
  attempt)`, the same shared draw and functional form every pass-catcher already uses. (2) a
  qualifying pass-catcher's target/carry share was computed against the sum of only *other
  qualifying* pass-catchers' volume, then multiplied against the team's *full* simulated
  volume — two mismatched denominators that inflated every qualifying player's output (caught
  when a real 316-point 2024 WR1 season simulated to a 504-point mean). Fixed by normalizing
  share against the team's real total volume (all positions, all players) instead.
- **A real RNG-reproducibility bug, caught by writing the reproducibility test rather than
  assuming it would pass:** `_pass_catcher_shares`/`_rb_shares` built their result from an
  unordered SQL `GROUP BY`, and the simulation draws each player's noise sequentially from one
  shared seeded `np.random.Generator` in dict-iteration order — DuckDB doesn't guarantee
  `GROUP BY` row order without an explicit `ORDER BY`, so which named player got which slice of
  the seeded random stream was query-plan-dependent, not code-dependent. Fixed with explicit
  `ORDER BY`s; verified reproducible both offline (11 new unit tests,
  `tests/unit/test_simulation.py`) and against real data (4 new live tests,
  `tests/integration/test_simulation_live.py`; 3 repeated real calls against KC 2024 produce
  bit-identical output to full float precision).
- **Model reproducibility, previously asserted by a fixed `random_state=42` in every model
  config but never actually tested:** added a new offline test
  (`tests/unit/test_established_ml.py::TestReproducibility`) that runs the real
  CatBoost/XGBoost/Ridge fit-predict path twice against identical synthetic data and diffs the
  persisted `evaluation_results` — genuinely exercising the claim rather than trusting the
  presence of a seed kwarg.
- **Secrets audit:** grepped tracked source for hardcoded credential patterns (none found);
  confirmed `.gitignore` excludes `.env`/`.env.*`/`data/`/`models/`/`*.duckdb`; confirmed
  `.env.example` files contain only placeholders; confirmed no data files or unusually large
  files are tracked in git.
- **Data-refresh, historical-reconstruction, and ambiguous-ID coverage reviewed** against the
  existing suite rather than assumed adequate: `tests/leakage/`'s `TestRebuildInvariance`
  already covers data-refresh consistency; `as_of`/`scrape_date` filtering is already tested
  across baselines/EDGE/league/leakage; `tests/unit/test_canonical_identity.py`'s
  quarantine tests already prove an ambiguous mapping is never inserted (and therefore can
  never silently join). Judged adequately covered rather than duplicated.
- **README, Makefile, and CI had drifted from the real system (D30), found while writing
  `docs/TRACEABILITY.md`:** `README.md` still documented the *original planning package*
  ("put this package into the repository..."), not how to install/run/use the system that was
  actually built — rewritten. `Makefile`'s `train`/`evaluate` targets referenced CLI flags that
  never existed on the real Typer CLI (verified broken by running them, not assumed); fixed,
  and added `market`/`edge validate`/`simulate`/`orchestrate` targets that had no Makefile
  entry despite being real since M8/M11/M13. No CI existed; added
  `.github/workflows/ci.yml` (lint + offline test suite on push/PR).
- `docs/TRACEABILITY.md` written: every `ACCEPTANCE_CRITERIA.md` checkbox mapped to the
  module/test/report that satisfies it, with every LIMITED/BLOCKED item's reason and fallback
  named explicitly rather than silently omitted.
- 15 new offline tests (204 total: 11 simulation + 3 REG/POST regression + 1 established-ML
  reproducibility) and 4 new live network tests (37 total, `test_simulation_live.py`).

## Post-M13: environment re-verification, and Sleeper trending as a real Weak-tier evidence signal (D31/D32)
This environment's network egress policy changed after M13 shipped. Re-verified live rather
than assumed (D31): Sleeper's public API is now genuinely `AVAILABLE`, no credentials needed;
FantasyPros/CFBD are network-reachable too, now blocked only on their still-missing API keys,
not policy.

Built on that: `evidence/sleeper_trending.py::detect_sleeper_trending` (D32) fetches Sleeper's
real `trending_adds`/`trending_drops`, resolves each to a canonical player via the existing
DynastyProcess `sleeper_id` crosswalk, and records `social_media_buzz` Weak-tier evidence
events through the same `record_event()`/taxonomy machinery every other detector uses — no
parallel evidence path. This is the evidence engine's first real Weak-tier detector
(previously registered vocabulary only, D5/D22). Wired into the CLI
(`alpha-squad evidence build-sleeper-trending`). Verified against real data: real Sleeper IDs
resolved to real players (Xavier Hutchinson, Barion Brown, Darren Waller, ...), 48/50 real
trending entries resolved on a real run.

Verifying it against real data caught a genuine, previously-undiscovered bug in
`evidence/prior_update.py::evidence_score_for_action` (already-shipped code from M9, not new):
its own docstring promised evidence "before that season's own Week 1" counts toward EDGE's
evidence score, but the code hardcoded an August 1st cutoff — real Week 1 dates run early
September (checked directly: 2023-09-07, 2024-09-05, 2025-09-04), so roughly five weeks of
real preseason evidence were being silently discarded, contradicting the function's own
documented intent. This had never surfaced before because no evidence source had ever
produced real events dated in August. Fixed to use the season's real Week 1 date from `games`
when known, falling back to September 1st only for a season with no games ingested yet.

7 new offline tests (211 total: 5 sleeper-trending unit + 2 evidence-cutoff regression) and 3
new/updated live network tests (39 total: 2 new sleeper-trending live tests, plus
`test_sources_live.py`'s Sleeper test flipped from asserting BLOCKED to asserting AVAILABLE,
exactly as its own prior docstring said to do if this ever happened).

**Then built (see D33 below):** real per-league Sleeper sync, and a multi-league registry so
multiple leagues (Sleeper-live and/or YAML) can be configured and switched between. **Still not
built:** live verification of the Sleeper field mapping against a real league (needs a real
Sleeper league ID, not supplied yet) and direct FantasyPros/CFBD access (needs API keys, not
supplied yet).

## Post-M13: multi-league registry — switch between multiple leagues seamlessly (D33)
The user has multiple real leagues, a mix of Sleeper and other/manual platforms, and asked to
switch between them seamlessly. Investigating first (rather than assuming the existing
`{league_id}` path parameters already did this) found they were vestigial: every CLI command,
the API, and the frontend hardcoded `target_league.yaml` regardless of what `league_id` was
passed in. There was exactly one league, config-driven, and nothing to switch between.

Built `league/context.py::resolve_league(league_id, ...)` and
`config/league_configs/registry.yaml` (`league_id -> {source: "yaml"|"sleeper", ...}`) as an
additive layer in front of the existing, unchanged `load_league_context()`: a `yaml` entry
resolves to a config file exactly as before; a `sleeper` entry hydrates a `LeagueContext` live
from a real Sleeper league on every call (never cached, so it can't drift from the real league's
current settings) via the new `league/sleeper_context.py::load_sleeper_league_context`. Every
call site that used to hardcode `target_league.yaml` — all 4 `league` CLI commands, the
`run_fantasy_strategy` agent, all `api/routers/league.py` endpoints, and `LeagueView.tsx` — now
resolves through the same registry, plus a new `alpha-squad league list` command / `GET /league`
endpoint / frontend dropdown (persisted across reloads via `localStorage`) to actually switch.
Verified in a real browser (Playwright): two leagues with deliberately different real settings
(14-team redraft/non-PPR vs. 10-team dynasty/PPR) switch correctly in both directions, with the
displayed data genuinely changing each time, not just a one-way fluke.

The Sleeper field mapping (`sleeper_context.py`) translates a real `/league/{id}` response into
`LeagueContext`: `roster_positions` counted into `lineup`/`roster` (bench vs. `IR`/`TAXI` split
out), `settings.type` (0/1/2) into `format` (redraft/keeper/dynasty), `scoring_settings.rec` into
PPR value, `settings.waiver_budget` into FAAB. Provenance (`source`, `sleeper_league_id`,
`sleeper_league_name`, `sleeper_season`) is stashed on the pydantic model via its existing
`extra="allow"` rather than a schema change. Building this against Sleeper's documented API shape
(no real league available yet to test against) surfaced a real naming inconsistency in the
codebase's own `FLEX_ELIGIBILITY` registry: Sleeper's real superflex slot is spelled
`SUPER_FLEX` (underscore); the already-registered key was `SUPERFLEX` (no underscore) — caught by
a new unit test, not live data, and fixed additively (both spellings now registered, so no
existing manual YAML using the unspaced form breaks).

11 new offline tests (222 total: 6 `resolve_league`/registry unit tests, 4 Sleeper-context
mapping unit tests, 1 API registry test) and 1 new live network test (40 total).

**Update (D34, same day):** the user supplied two real Sleeper league ids. The live test above
ran against both for real and passed, including `unrecognized_flex_slots == []` — confirming the
`SUPER_FLEX` fix (and the rest of `FLEX_ELIGIBILITY`) against real data, not just the documented
API shape. Both are now registered (`dilworth`: 12-team redraft/1QB/PPR; `boys_of_fall`: 10-team
dynasty/2QB/PPR) and switchable exactly like `target_league`. The Sleeper field mapping is no
longer "implemented but unverified" — it is verified.

**Update (D35, same day):** separately, real `FANTASYPROS_API_KEY`/`CFBD_API_KEY` values were
briefly committed to the tracked `.env.example` on `main` (a mistake, not this project's design —
the intended path is a gitignored `.env` or the deployment's own env-var config) and, since this
repo is public, were live-exposed until fixed. Fixed on `main` (`aa9e841`, restoring placeholders,
with the user's explicit go-ahead since `main` is outside this project's designated branch) and a
durable guardrail comment added directly in `.env.example` itself. The user was told to rotate
both keys at their providers regardless of the repo fix, since a repo-side fix cannot undo a
credential already having been public. See D35 for the full account.

**Update (D36, 2026-08-23):** re-verified in a fresh container. `CFBD_API_KEY` is confirmed picked
up and live — all 3 CFBD datasets (`teams`, `player_usage`, `recruiting_players`) return real
data; direct CFBD access is now AVAILABLE, no longer pending. `FANTASYPROS_API_KEY` is also
confirmed picked up (present, sent as the `x-api-key` header) but FantasyPros's own API rejects it
(`403 Forbidden`) — network policy is not the blocker (confirmed via raw response headers showing
a real AWS API Gateway/CloudFront response, not a proxy error), so this is not a repeat of the
"not yet picked up" state; it needs the user to check the key itself at FantasyPros's dashboard.
See D36 for the full account.

**Update (D37, 2026-08-23):** the FantasyPros `403 Forbidden` above was not a key problem — the
user confirmed the key was already correctly rotated, which prompted checking FantasyPros's own
API docs instead of continuing to suspect the key. `sources/fantasypros.py`'s base URL was missing
a `/public` path segment. Fixed; both FantasyPros datasets now confirmed AVAILABLE with real data.
Direct FantasyPros access is no longer pending or blocked. See D37 for the full account.

**Still not built:** manual/non-Sleeper league configs for the user's other leagues — needs the
actual league details (teams, scoring, roster slots) from the user, not supplied yet.

## Known limitations (see docs/DECISIONS.md for full reasoning)
- **Update (D37, 2026-08-23):** FantasyPros is now also fully AVAILABLE — the `403 Forbidden`
  reported below (D36) was a wrong adapter base URL, not a bad/unrotated key; fixed. Both CFBD
  and FantasyPros now return real data with their configured keys. See `docs/DATA_SOURCES.md`
  for the current, authoritative status.
- **Update (D36, 2026-08-23):** CFBD is now fully AVAILABLE with a live `CFBD_API_KEY` (real data
  confirmed across all 3 datasets). FantasyPros still isn't — a `FANTASYPROS_API_KEY` is present
  and being sent, but FantasyPros's own API rejects it with `403 Forbidden`; this is not a policy
  block, and root cause isn't established (needs the user to check the key). See `docs/DATA_SOURCES.md`
  for the current, authoritative status.
- **Update (D31, 2026-08-22):** the line below described the environment as it stood through
  M13. The network policy has since changed: Sleeper is now genuinely AVAILABLE (no code
  change needed — verified with real data), and FantasyPros/CFBD are network-reachable and
  blocked only on their still-missing API keys, not policy. KeepTradeCut (no adapter exists)
  and ESPN (unused) are the only sources still actually inert. See `docs/DATA_SOURCES.md` for
  the current, authoritative status.
- FantasyPros API, CollegeFootballData, KeepTradeCut, ESPN direct APIs were `BLOCKED_BY_POLICY`
  in this environment through M13; Sleeper, CFBD, and FantasyPros have since cleared (D31/D36/D37),
  KeepTradeCut and ESPN have not. Verified open-data
  substitutes are wired in regardless (docs/DATA_SOURCES.md). Adapters for the still-blocked
  sources are implemented but inert.
- Per-expert accuracy weighting: LIMITED to source-level weighting (D4).
- Automated news/social evidence ingestion: LIMITED to structured official signals (D5).
- ADP-implied baseline: LIMITED to the ECR-implied substitute; no independent ADP series is
  reachable (D16).
- Rookie college production: LIMITED, now for a *measured* reason rather than a missing source.
  D20 found no verified ID bridge from cfbfastR-data's numeric IDs; D38 built a real one via
  CFBD/`espn_id` and ingested the data; **D39 ran the ablation and did not adopt it** — college
  usage share is neutral-to-slightly-worse than the 12-feature baseline over identical
  walk-forward folds, including when restricted to high-coverage draft classes. Production stays
  on draft capital + combine + landing spot. Re-measurable any time via
  `train rookie --ablation` (reports/rookie_college_production_ablation.md).
- EDGE `evidence_score`: LIMITED to a disclosed neutral placeholder (0.5) until M9's evidence
  engine exists; never used to gate an action (D21).
- EDGE is single-season/redraft-horizon only (`rsf`), matching the M6 model's own horizon; a
  dynasty-horizon EDGE using `dsf`/`dynasty_values.value_2qb` is deferred to M10's trade logic
  rather than conflated with a single-season points model (D21).
- Historical EDGE validation: the BUY cohort's real out-of-sample outperformance is a strong,
  consistent positive signal (3/4 scored seasons decisively positive, the 4th essentially flat)
  and the SELL cohort moved the same direction as the market's real mistake in 3/4 seasons —
  not hidden, and recomputed in M13 after fixing a data bug that had been inflating some of
  these numbers; see M13 summary below and D28.
- Evidence Medium/Weak tiers (beat writers, coach comments, social media, practice-participation
  narrative): LIMITED to a registered taxonomy + manual-entry path; no reachable news/social API
  in this environment (D5, D22). Only Strong-tier, officially-sourced structured signals have a
  real detector.
- EDGE `evidence_score` was structurally near-always neutral in practice for the preseason-
  anchored EDGE, since the four Strong-tier detectors are in-season only and EDGE is preseason
  (D23) — a genuine horizon mismatch, disclosed rather than papered over. **Partially closed in
  D32**: Sleeper trending adds/drops is a real evidence source that exists *at* the preseason
  horizon (unlike the Strong-tier detectors), and a real bug in the evidence cutoff itself
  (hardcoded to August 1st despite the code's own docstring promising "before Week 1," which
  is early September — found while verifying D32 against real data) was silently discarding
  roughly five real weeks of any preseason evidence that did exist, for every season. Still
  true: the four Strong-tier structured detectors remain in-season only; an in-season EDGE
  variant that would let evidence meaningfully move `evidence_score` beyond a veto is future
  scope.
- Dynasty trade's age-curve adjustment is a documented heuristic (D25), not a trained/validated
  model — no ground-truth dynasty-value-decay dataset exists in this environment to fit one. It
  is a disclosed secondary adjustment only; the primary BUY/SELL signal is M8's real, validated
  EDGE.
- A real, disclosed cross-position calibration question (not a bug): on real 2025 data, M5/M6's
  point predictions at rank ~18-26 favor WR enough that M10's real VBD allocation sent every
  FLEX slot to WR rather than splitting across RB/WR/TE. M5/M6 passed their own baseline/
  calibration gates in aggregate; this is a downstream reminder that aggregate MAE doesn't
  guarantee cross-position relative calibration, worth revisiting in a future model-refinement
  pass — not addressed in M10, which correctly allocates flex by whatever values it is given.

## Post-M13: first real end-to-end pipeline run, and the college-production feature measured and rejected (D39)

The database in this container was empty before this run — D38's work had never executed against
real data. The full pipeline was run for the first time (2012–2025): 155 successful source
fetches, 25,050 players, 241,208 player-weeks, 26,816 player-seasons, 1,360 rookie-seasons,
5,566 college-usage rows across 1,541 players.

**The headline result is a negative one, and that is the point.** D38's CFBD college-production
features were measured against the pre-D38 baseline over identical walk-forward folds, under a
decision rule fixed before any numbers were seen, and **did not earn their place**: breakout
Brier +0.0030 (worse), regression Spearman −0.0003, MAE +0.0589. A robustness check restricted to
draft classes where the feature is ≥83% populated — testing whether zero-imputation of
low-coverage classes was masking a real signal — came out worse still, with the baseline winning
all four metrics. `FEATURES` reverted to the 12-feature D20 set; the data pipeline, identity
bridge and ablation harness are all kept so the question re-runs with one command.

**Running it for real surfaced three bugs that no test caught**, the most serious being that
`init_db` had no migration path: every DDL statement is `CREATE TABLE IF NOT EXISTS`, which
silently ignores a *column* added to an existing table. D38 was therefore broken-on-upgrade for
any pre-existing database — `features build` hard-crashed — while the entire test suite passed,
because every other test builds a fresh in-memory database. Also fixed: the ablation's own
fold-pairing (which produced a plausible-looking but fabricated +13.69 MAE result before being
caught as implausible), and `load_rookie_class_data` hardcoding the production feature list.
`tests/unit/test_schema_migrations.py` now builds the *old* schema first — the one case the suite
never exercised. 254 offline tests passing. See D39 for the full account.


## Post-M13: the incoming rookie class is now projectable (D40)

The app was showing the 2025 rookie class in August 2026 — a backtest presented as a forecast,
with the incoming class missing entirely. Three chained defects: nflverse's `players` file lags
the draft (all 694 `rookie_season=2026` rows have NULL draft capital) while `draft_picks` already
has the full 2026 draft but keys it on `esb_id` rather than `gsis_id` for that class only; the
spine upsert could never refresh draft capital once a row existed; and `rookie_features` is by
construction a *labeled* table that cannot hold a class whose season hasn't been played.

Fixed with an esb_id-fallback COALESCE in the spine build, a COALESCE-refresh on the upsert, and
a new `rookie_projection_features` + `alpha-squad train rookie-project --draft-class 2026`, which
writes predictions but deliberately no evaluation metrics (there is no outcome to score against).
The feature SQL and the imputation are shared verbatim between the labeled and unlabeled paths so
they cannot drift. The UI now asks the API which classes exist and defaults to the newest instead
of a hardcoded year.

2026 projection (trained on classes 2000-2025, 234 players): Jeremiyah Love 233.3 / 88%,
Carnell Tate 202.8 / 48%, Fernando Mendoza 196.3 / 86%, Ty Simpson 177.4 / 57%, KC Concepcion
139.9 / 15%. 259 offline tests passing.

**Known limitation:** Rankings, EDGE and League still default to the 2025 season, because the
data behind them genuinely stops at 2025 — projecting the 2026 NFL season for established players
is separate work. Changing those defaults without generating the data would show empty views.

## M15 summary — user-facing productization (D53)

Full detail in D53. The short version: the intelligence existed (M1-M14) but nothing let an actual
fantasy manager connect their real league and be told what to do. This milestone is the connect →
understand → analyze → decide → explain path, built entirely on top of already-tested M1-M13
tables and M10 recommendation functions — no new scoring or decision logic anywhere, frontend or
backend.

New: runtime Sleeper league onboarding (validated live before persisting, `registered_leagues`
table), real roster import bridged to canonical player ids, My Team roster intelligence, an Action
Center (ranked ADD/DROP/TRADE — three lists, not one fabricated composite score), batch waiver
ranking, a Player Detail view that explicitly separates universal player value from my-league
value for the same player, and Draft/Dashboard/multi-asset Trade-package views. A shared
`LeagueProvider` context replaced every view's own independent league dropdown.

Exercising the whole thing end to end with Playwright against a real backend and a real Sleeper
league (rather than trusting the code) found and fixed six real bugs: three DuckDB/refetch
concurrency issues (`init_db` running per-request instead of once at startup; `build_action_center`
re-fetching the live roster 3-4x per request; `duckdb.connect()` itself racing under concurrent
requests), a Sleeper snapshot-filename collision (missing the `param_suffix` fix already applied to
the other three source adapters), a non-atomic snapshot write that raced under concurrent
same-key reads (reproduced directly: 5,292 torn reads out of ~2,000 concurrent reads against the
old pattern, 0 against the fix), and a UI bug where a success confirmation was unmounted in the
same render batch that set it, so it never painted. Every fix has a regression test verified to
fail without the fix.

350 offline tests passing (up from 303); `make lint` clean; `tsc --noEmit` clean. Not built:
runtime "connect" for a manual/YAML league — `teams_for_league` returns `None` rather than
fabricating a roster for it, and the UI says so rather than showing a broken or fake roster.

## M16 summary — empirical validation & benchmarking phase (D54)

M15 productized the intelligence; M16 asked the harder question the product-facing work never
answered: does Alpha's intelligence actually produce better fantasy-football decisions than
strong, reasonable baselines, adversarially tested rather than assumed? Full methodology in
`docs/EVALUATION_PLAN.md`, real-data constraints in `docs/EVALUATION_LIMITATIONS.md`, full
results in `docs/ALPHA_VS_BASELINES_EVALUATION.md`, and the pre-registered-before-results
commitments plus a condensed results summary in `docs/DECISIONS.md` D54.

New `src/alpha_squad/evaluation/` package (8 modules, each also an `alpha-squad evaluate <name>`
CLI command): projection benchmarking against 3 baselines, a 5-tier market-inefficiency
stratification, a reusable historical draft-simulation engine (4 strategies x 5 real seasons x
10 draft slots), waiver-tier value discovery, rookie-vs-baseline benchmarking by round tier,
dynasty pick-value/age-curve validation against real outcomes, trade-evidence extraction, and
failure analysis. Every threshold, strategy, and season range was fixed in source and documented
in D54 *before* being run against real data.

**The headline result is unfavorable, and reported as such.** Alpha's underlying player-value
model (`ml_season_catboost`) beats every baseline on MAE at every position — the modeling layer
is validated. But the real historical draft simulation shows `alpha_league_aware` (the actual
production draft recommender) losing to plain market consensus on mean starter points in
**every one of the 5 real seasons tested**, never winning a single season outright, and scoring
below `alpha_bpa` (identical player values, no league context) on pooled total roster points
(though it *beats* `alpha_bpa` on pooled starter points — a real, mixed nuance: league context
helps the started lineup, it just strands more value on the bench overall). Root-caused not
just from the final rosters but by replaying the real `recommend_draft_pick` function
pick-by-pick against real 2021 data: the recommender drafted 7 QBs and zero RBs into a league
starting 2 of each in one real trial, and 12 WRs against only 3 QBs in another. Two compounding
mechanisms: `roster_fit_multiplier`'s real penalty growth is far gentler than its [0.7, 1.3]
bound implies (only a 6% discount at the 7th same-position pick, verified by direct
computation), nowhere near enough to overcome a real VORP edge; and the other 9 real
market-consensus opponents drain the scarce position at a normal rate throughout, so by the
time need-pressure would organically correct course, no usable players are left at that
position (round 16 of the replayed draft: best available RB had VORP -135.4). This is a
decision-logic bug, not a modeling one, and is the single most actionable finding of this
phase.

**A fix for the first mechanism was implemented and re-verified against a full re-run, per
explicit request.** `roster_need`'s oversaturation coefficient was steepened so
`roster_fit_multiplier` hits its 0.7 floor immediately at one player past a full bench,
instead of ~15 extra players. Result, reported honestly rather than oversold: pooled starter
points improved 1644.5 -> 1688.2 (+2.7%, a real gain in the metric that actually determines
fantasy outcomes) and the replayed 2021 roster's QB count dropped 7 -> 6, but pooled total
points worsened 2680.0 -> 2606.6 (a real tradeoff, not a free win). The fix does **not** close
the gap — `alpha_league_aware` still loses all 5 seasons (0/5 wins, unchanged) and still
trails `market_consensus` by 332.5 pts pooled (down from 376.2, ~12% of the gap closed). The
2021 roster still drafted zero RBs even after the fix, confirming the second mechanism
(positional-scarcity blindness) is untouched and is now the clearly-identified remaining work.

This finding was independently re-verified after the fact, prompted by a direct question about
whether pre-2025 training data was genuinely separated from 2025 outcomes: that audit found and
fixed two real bugs in the draft-simulation path itself (not methodology changes) —
`next_pick_survival_probability` had no season scoping at all (a historical draft could see
market data recorded years later), and several `min`/`max`/`.sort()` calls broke ties over
Python `set`s with no secondary key, which is non-deterministic across process runs because
`PYTHONHASHSEED` is unset here and real ties are common in the data. Both fixed with regression
tests, then verified (not assumed) by re-running the simulation twice in separate processes and
confirming byte-identical reports. The corrected numbers required one factual fix — an earlier
claim that market consensus won outright in all 5 seasons was wrong; it wins 4 of 5, with
`generic_prior_year` edging it out in 2025 specifically — but the core finding (Alpha's draft
engine never wins) is unchanged and now rests on a leak-free, reproducible basis.

Two other results are worth flagging: the 5-tier market-inefficiency test validates the
existing EDGE evidence gate (D21) specifically — raw disagreement magnitude alone is *not*
monotonic with outcome, only the evidence-gated BUY/SELL tier is — and Alpha's rookie model's
real edge is concentrated in late rounds (5-7) where draft capital alone is weak, while
early/mid rounds remain a genuine draft-capital-baseline win. Four real software bugs (a
position-misclassification and a season-intersection bug in `projection_benchmark.py`, the two
draft-simulation bugs above, plus a `zip(..., strict=True)` crash that only triggers on a
cleanly monotonic result) were found and fixed by this phase's own test suite before any
number was treated as final — see D54.

## M17 summary — draft-engine forensic audit (diagnostic phase, not a redesign)

M16 found and partially fixed the draft engine's roster-balance failure; this phase's explicit
purpose was to diagnose *why* it happens before attempting any further fix, per its own
instruction not to tune the engine against benchmark results. Full account:
`docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` (root cause), `docs/DRAFT_CONTROLLED_EXPERIMENTS.md`
(ablation results), `docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` (proposed fix, not
implemented), `reports/draft_decision_trace.json` (machine-readable pick-by-pick traces).

**A real, previously-undocumented finding: `positional_scarcity()` — a real, tested production
function required by `PRODUCT_SPEC.md`/`ACCEPTANCE_CRITERIA.md` and already consulted by the
waiver engine — is never imported or used by the draft engine (`league/draft.py`).** The
acceptance criterion "positional scarcity is calculated" is technically true (the function
exists and is exercised elsewhere) but the actual draft decision never consults it. A second,
related finding: `roster_need`'s "healthy bench depth" assumption (`slots + 2`, a hardcoded
constant) has no relationship to the league's actual configured bench size
(`league.bench_size`, a real property that turned out to be dead code before this phase).

**The core diagnostic finding, from replaying the real, unmodified `recommend_draft_pick`
pick-by-pick against real 2021 and 2025 data:** both traced pathological drafts (the same "7
QB/0 RB" and "12 WR/3 QB" examples from D54) are effectively decided by the team's first 1-2
picks, not a multi-round feedback loop. A real, viable RB was a live top-5 candidate at pick #1
in both cases and fell out of consideration entirely by the team's second pick (19 picks later
across the whole league) — never recovering until the position was already below replacement
level. The engine's score has no representation of "this position depletes fast, secure it now"
at the one point it would have mattered — only a single-candidate survival probability, never a
positional one.

**The simulator itself was validated as sound before trusting any of the above:** 90 real
homogeneous-league drafts (3 independent real strategies — market consensus, raw projected
value, and bare VORP — each drafting all 10 slots, removing the fixed-opponent-field design used
elsewhere) never produced a zero-RB roster once. Only TE occasionally went to zero, matching the
well-known, legitimate real fantasy strategy of "punting" a shallow-demand position — not a
simulator defect. This directly rules out the simulator and the player-projection model (already
separately validated, D54 §1) as root causes.

**Controlled ablation at full scale (400 real drafts: 5 seasons × 10 slots × 8 tiers, each tier
adding one mechanism from the directive's list on top of the last) confirms the single-slot
finding generalizes, with one important, counter-intuitive refinement.** The real production
engine zeros RB in 10 of 50 trials — concentrated entirely in the real 2021 season (10/10 slots
that year, 0/10 in every one of 2022-2025; why 2021 specifically remains open). Adding current
positional scarcity, analytical future scarcity, or a literal opponent-behavior replay each made
the RB=0 rate *worse* (32%, 32%, and 36% respectively) than plain roster-fit alone (20%) — a
real, tested, negative result, not smoothed over: `positional_scarcity()`, the exact real
production function required by `PRODUCT_SPEC.md` and already used by the waiver engine, rates
QB as the most "scarce" position in real 2021/2023 data and RB as one of the least, reinforcing
the QB-stacking side of the same pathology rather than fixing the RB side. Only an explicit,
points-denominated opportunity-cost term (Experiment F) both cut the RB=0 rate to 4% and
improved mean starter points above the current production engine (1789.1 vs. 1688.2 pooled,
winning 4 of 5 real seasons) — despite inheriting the same QB-favoring scarcity distortion every
other tier from C onward carries, making its improvement the more notable for overcoming that
headwind rather than avoiding it.

**No further fix was implemented in this phase, per its own explicit instruction.** The
recommendation is a moderate-complexity addition (an explicit per-position opportunity-cost
term, priced continuously, using an opponent-behavior replay as its input, deliberately *not*
layering in `positional_scarcity` given the finding above) — not a rebuild, not a hardcoded
positional cap, not a full Monte Carlo lookahead — with the honest
caveat that its sufficiency at full scale, and in combination with the already-landed
saturation-penalty fix, remains `UNKNOWN` and must be measured before being claimed as solved.


## M18 summary — positional opportunity cost shipped to the draft engine (D55)

M17 diagnosed the draft engine's root cause without fixing it; M18 implemented the fix, measured
it on the official benchmark, and recorded what it did and did not achieve. Full account:
`docs/DECISIONS.md` D55.

**The recommendation was not implemented as written, and that mattered.** Verifying
`docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` against the source before building found its
proposed formula (`production + opportunity_cost`) had never actually been measured: Experiment
F — the number the recommendation rested on — includes `positional_scarcity` (the mechanism the
experiments proved harmful) and excludes production's confidence and survival terms. A new
pre-registered P-tier ablation (300 real drafts, decision rule committed to source before
running) resolved it. The integrated form that won, `(VORP + opportunity_cost) × fit × risk ×
survival × [cap]`, beat both the recommendation's raw additive form and Experiment F itself.

**Measured on the official `alpha-squad evaluate draft-simulation` benchmark, full 2021-2025:**
mean starter points **1688.2 → 1801.1 (+112.9, +6.7%)**. Alpha's draft engine moves from 3rd of
four strategies to 2nd, now ahead of the non-market `generic_prior_year` baseline it previously
trailed. RB=0 rosters fell 10/50 → 2/50. The D54 QB-stacking pathology is materially reduced:
7-and-8-QB rosters (9 of 50 before) no longer occur at all, max QB 8 → 6, concentration index
0.345 → 0.304. All 10 draft slots improved; none regressed. The benchmark reproduced the
diagnostic harness's prediction to the decimal, per season.

**Mechanism verified from the decision trace, not inferred from roster counts.** Re-tracing the
2021 slot-1 pathological draft: pick #1 is now RB where it was TE, and the engine's own reason
string states why — *"RB opportunity cost +60.5 pts"*. The RB wins **despite lower VORP** than
the TE it beat. 2025 slot 1, which never had the pathology, is essentially unchanged: the term
is targeted, not a blanket re-weighting.

**Reported regressions, not just gains:** 2023 lost 6.4 starter points (0.35%); pooled total
roster points dipped 6.8; the feasibility cap fires on every draft both before and after. Most
importantly, **`market_consensus` still leads by 219.6 starter points and Alpha has still never
won a single season against it** — `docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0's acceptance
criterion remains unmet. Determinism passed (two separate-process benchmark runs, byte-identical)
and runtime cost is negligible (+0.099 s/call, +3.4%). 474 offline tests passing (up from 450);
lint and `tsc` clean.

## M19 summary — 1-QB target format retarget: Alpha beats consensus (D56–D60)

The product's target format changed from 10-team 2QB dynasty (D7) to 10-team 1-QB redraft
(`docs/TARGET_FORMAT_1QB.md`). This milestone audited every format-dependent assumption in the
codebase against the new format, found that the audit invalidated the project's entire recorded
draft evaluation, re-baselined it correctly, and closed `docs/IMPLEMENTATION_GAP_ANALYSIS.md`'s
P1-0 — the acceptance criterion open since M16. Full account: `docs/DECISIONS.md` D56–D60,
`docs/FORMAT_MIGRATION_DIAGNOSTIC.md`.

**The benchmark itself was wrong, not just the target.** `ecr_type='rsf'` — the board every
prior draft evaluation ran against — is FantasyPros' *superflex* board (9 of the real
preseason-2024 overall top 15 are QBs; the 1-QB board `ro` has none in its top 15). It was the
correct board while the target league was 2QB (D21); it measures a different game now. A second,
independent bug compounded it: `ecr_type` alone is not a rank space — DynastyProcess labels an
IDP board with the same `ecr_type` as the real PPR board, and the pre-fix primary key silently
dropped one of the two whenever they collided on a date (D56). `market_snapshot.page_type` and
`market/series.py::resolve_market_series` fix both; every pre-D56 draft number is retained,
labelled by the format it measured, not restated.

**K and DEF, the new format's two new starting slots, had three separate gaps, all real and now
closed (D57).** Kickers were ingested but scored 0.0 (nflverse prices only
passing/rushing/receiving); team defenses did not exist as an entity anywhere; FantasyPros' DST
market ranks were dropped at ingest. All three are now computed from real data — kicker points
from real FG/PAT components, DST from real defensive stats plus real points allowed, DST market
rank via a 3-entry team-code alias map. Both get measured baselines, not models, with the
weighting chosen by walk-forward MAE over real 2015–2025 seasons (K: weighted 2-year, MAE 33.60;
DST: shrunk hard to the positional mean, MAE 22.55) — an ML model would imply precision neither
signal supports (K r=0.41, DST r=0.29 year-over-year).

**Two format-shaped defects in previously-correct mechanisms (D58).** Positional capacity split
the bench evenly across dedicated positions and ignored FLEX entirely — survivable at 4
positions and a 2-QB lineup, first-order wrong once K/DEF joined the lineup (RB capped at 3 in a
league starting 2 RB + up to 2 FLEX). `roster_need`'s depth target was the arbitrary constant
`slots + 2`. Both now derive from the league's own config (`positional_capacity`,
`startable_slots`). The config's own roster arithmetic was inconsistent (9 starters + 10 bench
declared alongside `roster_size: 17`); now 10 + 6 = 16, asserted by test for every shipped
config.

**Re-baselined, with no engine change: Alpha already won.** `alpha_league_aware` (D55's shipped
formula, unmodified) on the corrected `ro` board and 1-QB config: 1927.8 mean starter points vs.
`market_consensus`'s 1825.2 (+102.6, +5.6%), 34/50 (68%) win rate, winning 4 of 5 seasons — the
reverse of every pre-D56 result (D59).

**Marginal starter value, measured and shipped (D60).** The audit re-asked M17's open question
under the new format rather than assuming the answer transferred: does the engine understand
whether a candidate would actually improve the team's starting lineup? It did not — VORP prices
against league-wide replacement level, `roster_need` against a positional count, neither knows
whether a specific candidate would start *on this specific roster*. `marginal_starter_value`
supplies that. A pre-registered M-tier ablation (200 real drafts) found replacing VORP with it
outright (tier M3) strictly won: +109.7 starter points (+5.8%), 37/50 win rate, zero infeasible
rosters — and was the only tier that fixed a real, previously invisible defect: the VORP-based
formula drafted a mean 3.78 kickers and 2.26 defenses per 16-round draft, because a bench K/DST
still scores positive VORP despite zero chance of ever starting (neither has flex eligibility).
Shipped as an additive, backward-compatible parameter (`roster_player_ids`) so callers without
real per-team roster tracking see no behavior change.

**Official benchmark, full 2021–2025, determinism verified:**

| Strategy | Mean starter pts | vs. consensus |
|---|---|---|
| `alpha_league_aware` (D60) | **1990.9** | **+165.7 (+9.1%)** |
| `market_consensus` | 1825.2 | — |

Win rate: **37/50 (74%)**. Wins 4 of 5 seasons; 2024 is a near-miss (−10.1, down from D55's
−80.1 measured under the same board). Two separate-process runs are byte-identical
(`md5 5e0ec53e...`). **`docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0's acceptance criterion is now
met** — the fix that closed it was selected by a pre-registered decision rule measured against
the corrected benchmark, not chosen to hit the target.

602+ offline tests passing (up from 474); lint and `tsc` clean. New: `market/series.py`,
`features/kicking_defense.py`, `models/baselines/kicking_defense.py`,
`evaluation/pick_attribution.py`, M-tiers in `evaluation/draft_forensics.py`,
`docs/TARGET_FORMAT_1QB.md`, `docs/BENCHMARK_SPEC.md`, `docs/FORMAT_MIGRATION_DIAGNOSTIC.md`.

---

## D84 — Trust audit of the whole draft path (third pass). Nothing shipped.

**Status: `league/` and `models/` byte-identical to Y1.** Full record: `docs/DECISIONS.md` D84.

Opened on D83's closing question (is the value base drawing replacement at the wrong boundary?).
Answer: **the hypothesis as posed is refuted, and a sharper defect is now measured and named.**

* **The starter-vs-consumption question is settled and the answer is "neither".** Moving
  replacement to the starter boundary *widens* the round-2 QB margin (+38.6 → +48.5), because it
  raises RB's replacement more than QB's and so amplifies the raw-projection term. The
  consumption/starter gap at QB is also larger in 2QB (145.4) and superflex (104.7) than in 1QB
  (60.1), where the engine's early-QB behaviour is correct — so it is not a 1-QB pathology.
* **The real defect is the double count, and it is provable at K.** The engine takes a kicker at
  pick #80 valued at 224.5 (`2·182.4 − 140.4`) when its own board says the best kicker is still
  free at pick **#141** — a true marginal value of 0.0. Four of the top five candidates at #80 are
  kickers.
* **Every fix loses.** Experiment T (pre-registered, `91c5ab9`) tested timing-aware (VONA)
  replacement in three forms: −29.5, −163.3 and −0.1 starter points. That makes eight value-base
  reformulations measured across D63/D79/D84, all losing.
* **The benchmark cannot price the defect.** Bench players score zero realized starter points, so a
  wasted bench slot is free by construction. Diagnostic arms that defer K/DST cost −16.7/−18.3
  (unresolvable); deferring QB costs −79.7 at round 5 with a CI **excluding zero**.
* **The elite-RB error is largely not Alpha's.** The free consensus market under-projects the same
  players by +35.2 against Alpha's +42.3, and shares the sign of every other tier bias (WR 11–24
  over-projected, QB top-10 over-projected — where the market is *twice* as biased). Correcting the
  elite-RB cell to a market-grade projection changes **no decision Alpha makes** (verified as a real
  null, not a silent no-op).
* **Experiment N (pre-registered, `1ad9dfe`) refutes the model-family hypothesis.** Linear, isotonic,
  shrinkage and hybrid estimators all make the RB elite tail worse (+19.5, +20.2, +0.7, +8.7 MAE);
  a walk-forward blend given a free choice selects the tree outright.

**Benchmark, re-measured on a from-source rebuild:** Alpha 2013.5 vs fair consensus 2034.8
(**−21.3**, CI [−141.5, +99.0], 2/5 seasons). D79 §10a measured **+21.2** for the identical
comparison — the margin has no stable sign, exactly as D71's power analysis predicted. The gap to
`alpha_bpa` (417.8) is unambiguous: the league-context layer is doing very large work.

**Confirmed end to end on the production path:** 60 full drafts (2021-2026 x 10 slots) through the
real `recommend_draft_pick` return a mean 2021-2025 starter total of **2013.5**, identical to the
counterfactual harness's control. Across seasons the opening is board-dependent (first pick WR
46/60, RB 9/60, QB 5/60; 2021 opens `RB-TE-WR`), so the 2026 board's WR-first/QB-early figures do
not generalise. **The early kicker does: a kicker is taken by round 10 in 60 of 60 drafts** (mean
round 8.75), on every board and from every slot -- the engine's single most reproducible behaviour,
and worth 0.0 by its own board.

**Highest-value next step is a better objective, not another value base.** The one thing that would
let the instrument see the defect it cannot currently price is a benchmark that models bench depth —
injuries, byes, waiver leverage, weekly lineup decisions.

Also fixed this pass: `make train` never built historical K/DST projections (`train
kdst-projections` is not one of its steps), so a from-source rebuild could not fill a K or DEF slot
for 2021–2025. 1181 offline tests passing. New: `evaluation/opening_audit.py`,
`evaluation/decision_counterfactuals.py`, `evaluation/timing_replacement.py`,
`evaluation/projection_shrinkage.py`.
