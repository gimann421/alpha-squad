# D110 — Cross-position magnitude sensitivity

**Status: COMPLETE.** The pre-registration below was committed (`a90b2dd`, amended `f37d56a`)
**before any arm ran**; results are appended at the end and nothing in the pre-registration was
changed after an arm result was seen.

Diagnostic/sensitivity experiment. No production change, no retraining, no new feature, no
calibration, no change to the scoring formula, no PR, nothing merged.

## The question

Not *"can we build a better projection model"*, but:

> **Is cross-position projection magnitude actually a causal lever in Alpha's early-round
> decisions, and is the effect large enough to matter in realized draft value?**

D109 established that Alpha is WR/QB-heavy in rounds 1–3 and delays RB; that Y1 has a real
cross-position magnitude defect concentrated at the RB upper tail; and that individual picks are
often robust to the observed error while the *aggregate* early-round construction is sensitive at
roughly the magnitude of that error. This phase isolates that axis before any calibration method
is considered.

## Frozen

Y1 model weights, the production decision engine (`league/`), board construction, draft format
(10-team 1-QB PPR, `roster_size` 16), the continuation/opponent policy, the seasons (2021–2025),
and all production code. Nothing is retrained. Nothing is tuned against realized outcomes.

## The transformation

    adjusted_projection = position_multiplier × Y1_projection

A strictly positive multiplier is monotone, so **within-position order is preserved exactly**;
only the magnitude of one position relative to the others moves. This is deliberately *not*
quantile calibration, isotonic regression, Platt scaling, empirical Bayes, or any learned map.

Applied in an isolated database copy to **both** projection tables the engine's own loader reads:
`uncertainty_predictions.point_prediction` and `rookie_predictions.predicted_rookie_points`
(rookies are 143 of 714 RBs in this window, so scaling only the former would leave a fifth of the
position unscaled). Verified per position per season against `load_season_projections` before any
draft runs — D81 recorded that an override passed as an argument is a silent no-op.

**`confidence` is never touched**, so the engine's `risk` multiplier is byte-identical across
arms. D109 flagged risk as a suspect; holding it frozen keeps it a control here rather than a
confound. It is examined separately, as a diagnostic only.

Opponents draft by ECR, which no arm touches, so every arm faces an identical opponent field on
an identical board: trials are paired by `(season, slot)`.

## The grid (frozen before any result was seen)

Centred on Y1 = 1.00 and deliberately **coarse**. D109's implied RB correction is ≈ **×1.21**
(a −41.5 point bias on a mean projection of 197.1 inside ECR ≤ 30); the grid brackets that
generously in **both** directions. No direction is assumed correct.

**Value-scored arms** — as first registered, 5 seasons × 10 slots = 50 paired drafts each;
**reduced to 4 slots (20 drafts) by Amendment 1 below**, on runtime grounds, before any arm
result existed:

| arm | multipliers | purpose |
|---|---|---|
| `control` | all 1.00 | frozen Y1 |
| `rb_080`, `rb_090` | RB 0.80 / 0.90 | RB magnitude **down** |
| `rb_110`, `rb_120` | RB 1.10 / 1.20 | RB magnitude **up**, bracketing the implied ×1.21 |
| `rb_140` | RB 1.40 | far beyond any measured bias — does *any* magnitude help? |
| `qb_090`, `qb_110` | QB 0.90 / 1.10 | move QB instead of RB |
| `wr_090` | WR 0.90 | move WR instead of RB |
| `gap_rb120_wr090` | RB 1.20 + WR 0.90 | the D109-implied **gap** correction |

**Decision-surface-only arms** — 5 seasons × 4 slots (1, 4, 7, 10; the repo's own `DEFAULT_SLOTS`
from D103). Reported *only* as threshold resolution for Part 2, **never** as a value comparison:
`rb_095`, `rb_105`, `rb_115`, `rb_130`.

### Amendment 1 — slot count reduced from 10 to 4, on runtime grounds

Recorded before any arm-vs-control comparison existed. On the first launch a single draft took
**153 s** under 5-way contention (against 42.5 s measured solo), which put the 580-draft design at
roughly **7 hours**. All arms — value-scored included — therefore run at **4 slots (1, 4, 7, 10)**,
the same `DEFAULT_SLOTS` D103 uses, giving 5 × 4 = **20 paired drafts per arm** and 280 in total.

Justification is the repository's own prior finding, not convenience: **D88 measured that the
detection floor is bound by the number of independent season clusters and that slots cannot lower
it** ("MDE floors at ~56 regardless of slots — seasons bind, not slots"), and D89 corrected that
floor to 51.1 without disturbing the conclusion. Fewer slots make each season mean slightly
noisier but do not change what the experiment can resolve, and Part 6 re-derives the floor
empirically on this vintage rather than assuming D88 transfers.

**What had been seen at the time of this amendment:** one number — the control arm's 2021 slot 1
draft returning 2132.0 starter points, which is the D109 reproduction check, not an arm result.
No arm had been compared with control, and the grid itself is unchanged.

**Exclusion, stated in advance.** TE gets no arm: D109's TE bias (−17.0) rests on n=8 inside
ECR ≤ 30, and TE is taken in only 10 of 150 early picks, so a TE arm would buy threshold
resolution on a cell too small to interpret. A scope decision, not a finding.

## Metrics

**Primary:** absolute realized starter points of the full 16-round roster, per `(season, slot)`,
differenced against the control on the **same** `(season, slot)`.

**Explicitly not primary:** arm-relative pick regret. D105/D106 established it becomes
non-monotone once the arm itself changes the oracle comparison, and D106's matched regret ladder
self-invalidated for exactly that reason.

**Secondary/diagnostic:** rounds 1–3 vs 4–6 vs full-draft realized value (diagnostic only — the
whole-draft objective remains the north star); positional attribution of any value difference;
and a power check re-derived on this vintage against D109's ≈ +177 points/draft expectation.

## Instrument

`evaluation/draft_simulation.py::simulate_draft` with `ALPHA_LEAGUE_AWARE` — which calls
`league/draft.py::recommend_draft_pick` itself — against the fair roster-aware consensus opponent
field (`MARKET_CONSENSUS_ROSTER_AWARE`, D61 Stage 1.1). No parallel scoring implementation exists
in this phase. Cross-instrument parity check: `simulate_draft` returns 2132.0 starter points for
2021 slot 1, byte-identical to what D109's `audit_opening` reported for the same cell.

## Data vintage

The D109 rebuild — assembled board `combined_hash`
`d2955868ccf9714bbe087c896c4cec06df44659f18b7262ad48cf484fce25c1f`. The upstream DynastyProcess
board and identity map reproduce D89 byte-identically; the **nflverse panel underneath them was
restated upstream** (D109 §0). Numbers in this phase must **not** be compared against pre-D109
published figures as if they came from identical data. The runner records the vintage on every
row.

Runner: `scripts/research/d110_magnitude_grid.py` (committed before any arm ran).

---

# Results

*Appended after all 14 arms ran. The pre-registration above is unchanged.*

## BOTTOM LINE

Cross-position projection magnitude is a **very strong lever on what Alpha drafts** and a **non-lever
on what Alpha is worth**. Scaling RB projections moves the decision surface smoothly and hard — at
×1.40 the first RB arrives in round 1.80 instead of 4.35 and 42% of all rounds 1–3 picks change —
yet **no arm produced a realized-value improvement whose confidence interval excludes zero**, and
8 of the 9 value-scored arms are powered to have seen an effect the size D109 suggested. The only
statistically significant result in the whole grid is a *harm*: raising QB magnitude 10% costs
−39.3 points per draft, losing in 5 of 5 seasons. The apparent RB benefit (+30.8 at ×1.20, +81.4 at
×1.40) is **entirely one season** — remove 2024 and those become −3.6 and +18.7 — and in the single
draft with the largest gain the first three picks were *identical* to control, with the whole +548
coming from rounds 4–9. So the hypothesis that the early-round positional tilt is where the value
is fails on its own evidence.

## WHAT CHANGED

- **The decision surface responds smoothly and monotonically to `m_RB`.** First RB round: 6.20 at
  ×0.80 → 4.35 at ×1.00 → 3.05 at ×1.15 → 2.15 at ×1.30 → 1.80 at ×1.40. Round-1 RB share: 0% →
  20% → 55%.
- **The modal opening flips at ×1.20** (`WR-WR-QB` → `WR-RB-QB`) and again at ×1.40 (`RB-RB-QB`).
- **Rounds 1–3 picks changed:** 5% at ×1.05, 13% at ×1.15, 18% at ×1.20, 28% at ×1.30, 42% at ×1.40.
- **Moving WR down works about as well as moving RB up** for changing decisions: `wr_090` alone
  changes 27% of rounds 1–3 picks and pulls the first RB to 3.75.
- **Changes are overwhelmingly cross-positional** — 83 of 90 changed picks at ×0.80, 113 of 128 at
  ×1.40 — which is what the transformation was designed to do, and confirms within-position order
  was preserved.
- **`qb_090` barely moves anything** (3% of picks, only 3 of 20 drafts diverge at all), because QB
  is taken only where it already wins by a wide margin.

## DID IT HELP?

**No.** Not one arm improved realized draft value at 95% confidence, and this is a *powered* null
for 8 of 9 arms, not an absence of evidence.

| arm | mean Δ vs control | 95% CI (season clusters) | seasons | powered for ~177? |
|---|---|---|---|---|
| `rb_080` | −26.8 | [−105.3, +51.7] | 2W/3L | yes |
| `rb_090` | −5.8 | [−62.6, +51.1] | 2W/3L | yes |
| `rb_110` | −14.4 | [−35.1, +6.2] | **0W/5L** | yes |
| `rb_120` | +30.8 | [−84.9, +146.6] | 3W/2L | yes |
| `rb_140` | +81.4 | [−103.2, +266.0] | 4W/1L | **no** |
| `qb_090` | +9.1 | [−12.6, +30.9] | 2W/3L | yes |
| **`qb_110`** | **−39.3** | **[−59.0, −19.7]** | **0W/5L** | yes |
| `wr_090` | −44.6 | [−99.3, +10.1] | 1W/4L | yes |
| `gap_rb120_wr090` | +22.1 | [−104.3, +148.5] | 2W/3L | yes |

Control mean is 2019.0 starter points with a draft-to-draft sd of 194.1, so every effect above is
small relative to the noise a single draft carries.

## WHAT THIS MEANS

Of the seven outcomes pre-registered in the brief, the evidence selects **B — magnitude changes
many decisions but does not improve realized value** — with **D** attached in a specific and
unexpected form: what value movement exists comes from **rounds 4–16, not rounds 1–3**. Outcome C
is firmly rejected (decisions change a lot). Outcome A is rejected for every powered arm.

Three things make this more than a null:

1. **The one significant result points the other way.** `qb_110` is worse, consistently, in every
   season. That is a *degradation* result, and it corroborates D109's finding that QB is already
   over-weighted early — the engine does not need more QB magnitude, it has too much.
2. **The positive RB signal is a single season.** Excluding 2024: `rb_120` +30.8 → −3.6,
   `rb_140` +81.4 → +18.7, `gap` +22.1 → −13.0. 2024 is the season D109 already flagged as extreme
   (the hindsight oracle wanted an RB in 30 of 30 early states). One season cannot carry this.
3. **The early rounds are not where the points are.** In 2024 slot 1 — the largest single gain in
   the grid, +548 — `rb_140` and control take the **identical** first three picks; the divergence
   starts at round 4, and the gain is Barkley-class backs in rounds 4–9 replacing WRs. At the clean
   first-divergence comparison, swapping toward RB is value-neutral to negative (`rb_110` −32.7,
   `rb_140` −3.1, `rb_120` +4.3).

So the D109 finding stands — Y1's cross-position magnitudes really are wrong — but the inference
that correcting them would buy early-round draft value does **not** follow, and this experiment is
powered enough to say so rather than shrug.

One result worth keeping for its own sake: `qb_110`'s **first divergence gains +95.9 realized
points** (it takes the QB, and the QB outscores the WR/RB it displaced) while the whole draft ends
**−39.3** worse. Per-pick realized points and draft value are not the same quantity, and this is the
cleanest demonstration of it in the record.

## RISK MULTIPLIER

Read-only diagnostic; nothing was ablated, and D110's arms hold `confidence` frozen so it stayed a
control throughout.

- **It is partly a function of the projection it multiplies.**
  `confidence = clip(1 − (p90 − p10) / (2·|point_prediction|), 0, 1)` puts the point prediction in
  the denominator. Inside the rounds 1–3 contention set RB scores 0.604 against WR's 0.719, and
  decomposing that gap shows roughly **half comes from RB simply being projected lower** (148.2 vs
  129.2 absolute width, but 195.9 vs 234.4 projection). The D109 under-projection is therefore
  partly self-reinforcing.
- **It does carry real signal, but it is anti-correlated with bias.** Relative error falls
  monotonically across confidence quintiles (0.56 → 0.25), so it is not noise. But mean bias runs
  **−33.1 in the lowest quintile to +22.3 in the highest** — the multiplier marks *down* exactly the
  players who are under-projected and marks *up* those over-projected, compounding the error
  instead of hedging it.
- **Its leverage is wildly unequal across positions.** Within ECR ≤ 36 the multiplier spans
  **4.28× at RB** (0.168 → 0.719) against **1.13× at QB**. It is doing far more work at the one
  position D109 identified as under-projected than anywhere else.
- **It is an explicitly uncalibrated heuristic used as a direct multiplicative factor on value** —
  its own docstring says "a simple heuristic (not a probability) … deliberately not claimed as
  calibrated on its own", yet `league/draft.py` multiplies the value base by it unmodified.

## RECOMMENDATION

**Stop treating cross-position projection magnitude as the lever.** It is a real defect and a real
decision lever, but this phase shows — with adequate power on 8 of 9 arms — that correcting it does
not convert into realized draft value, and that the value movement it does produce is a
middle-round side effect concentrated in one season. Pursue the **risk multiplier** instead: it is
the one component that is uncalibrated by its own documentation, anti-correlated with the very bias
D109 measured, and swinging RB scores by 4.3× in exactly the round where the WR/RB question is
decided. It is also cheap to test, because ablating it to a constant is a single research-tier
change requiring no projection change at all.

---

# Evidence and methodology

## Decision surface — the full RB ladder

`m_RB` against behaviour; 20 paired drafts per rung, all against the same control cells.

| m_RB | R1 RB% | R1–3 RB% | 1st RB round | % R1–3 picks changed | modal opening |
|---|---|---|---|---|---|
| 0.80 | 0% | 0% | 6.20 | 20% | `WR-QB-WR` |
| 0.90 | 5% | 8% | 5.15 | 13% | `WR-WR-QB` |
| 0.95 | 10% | 13% | 4.80 | 8% | `WR-WR-QB` |
| **1.00** | **20%** | **15%** | **4.35** | — | **`WR-WR-QB`** |
| 1.05 | 25% | 18% | 4.10 | 5% | `WR-WR-QB` |
| 1.10 | 25% | 20% | 3.40 | 7% | `WR-WR-QB` |
| 1.15 | 30% | 22% | 3.05 | 13% | `WR-WR-QB` |
| 1.20 | 30% | 27% | 2.60 | 18% | **`WR-RB-QB`** |
| 1.30 | 35% | 35% | 2.15 | 28% | `WR-RB-QB` |
| 1.40 | 55% | 43% | 1.80 | 42% | **`RB-RB-QB`** |

**Thresholds, stated no more precisely than the grid supports:**

- **Pick #1 changes late.** At draft slot 1 the control takes WR in 3 of 5 seasons and RB in 2; that
  split is unchanged through ×1.30 and only becomes RB-majority (3 of 5) at **×1.40**. Moving WR
  *down* 10% flips it sooner (`wr_090`: RB 2, WR 2, TE 1).
- **The modal three-round construction flips at ×1.20.**
- **The first RB comes a full round earlier at about ×1.15**, and two rounds earlier at ×1.30.
- **Materially reducing WR concentration needs ×1.20+**: rounds 1–3 WR count falls 28 → 22 (×1.20)
  → 17 (×1.30) → 13 (×1.40) out of 60.
- Picks **#20/#21** are dominated by the snake turn and QB: #20 is QB in 5 of 5 seasons under
  control and stays QB-majority through ×1.40. Picks **#40/#41 and #60/#61** move only at ×1.20+.

## Where the value differences live

Realized points of the players *drafted* in each round block, differenced against control
(diagnostic only — these blocks do not sum to starter points, because starters are a subset):

| arm | R1–3 | R4–6 | R7–16 | all picks | **starters (primary)** |
|---|---|---|---|---|---|
| `rb_110` | −5.0 | −22.3 | +35.6 | +8.4 | −14.4 |
| `rb_120` | +13.9 | +6.0 | +30.6 | +50.5 | +30.8 |
| `rb_140` | **−0.1** | +32.7 | **+69.2** | +101.8 | +81.4 |
| `wr_090` | −18.7 | −39.7 | +22.9 | −35.5 | −44.6 |
| `gap_rb120_wr090` | −7.0 | +5.2 | +50.2 | +48.4 | +22.1 |

`rb_140`'s rounds 1–3 contribution is **−0.1**. The arm that changes 42% of early picks produces
none of its value there.

## Attribution

First divergence per draft — the only like-for-like comparison, since after it the two drafts face
different boards:

| arm | drafts diverging | mean round | position changed | Δ realized at that pick | swap |
|---|---|---|---|---|---|
| `rb_110` | 16/20 | 6.25 | 16/16 | **−32.7** | RB←WR 11, RB←TE 3, RB←QB 2 |
| `rb_120` | 18/20 | 4.50 | 18/18 | +4.3 | RB←WR 13, RB←QB 4 |
| `rb_140` | 20/20 | 3.00 | 20/20 | −3.1 | RB←WR 12, RB←QB 8 |
| `wr_090` | 16/20 | 3.75 | 16/16 | +21.9 | RB←WR 8, QB←WR 6 |
| `qb_110` | 11/20 | 2.64 | 11/11 | **+95.9** | QB←WR 6, QB←RB 5 |

## Power

MDE is reported per arm because an arm that changes more picks has a noisier paired difference —
the manipulations the phase most wanted to measure are the ones it measures worst.

| arm | sd(season) | MDE @95% | powered for ~177? |
|---|---|---|---|
| `rb_110` | 16.6 | 20.6 | yes |
| `qb_110` | 15.8 | 19.6 | yes |
| `qb_090` | 17.5 | 21.8 | yes |
| `wr_090` | 44.0 | 54.7 | yes |
| `rb_090` | 45.8 | 56.9 | yes |
| `rb_080` | 63.2 | 78.5 | yes |
| `rb_120` | 93.2 | 115.8 | yes |
| `gap_rb120_wr090` | 101.8 | 126.4 | yes |
| **`rb_140`** | **148.7** | **184.6** | **no** (needs 6 season clusters) |

8 of 9 arms could have detected an effect the size D109 suggested. `rb_140`'s +81.4 is the one
figure in the grid that must be read as underpowered *as well as* 2024-driven.

## Validity checks

- **Control reproduces D109.** 2021 slot 1 returns **2132.0** starter points through
  `simulate_draft`, byte-identical to what D109's independent `audit_opening` harness reported for
  the same cell — two different harnesses, same production engine, same number.
- **Every override verified to reach the engine's own loader**, per position per season, before any
  draft ran (`verify_arm`); D81 recorded that an override passed as an argument is a silent no-op.
- **Zero unfilled mandatory starting slots** across all 280 drafts in all 14 arms.
- **Within-position order preserved by construction** (a positive multiplier is monotone), and
  confirmed empirically: 83–96% of changed picks are cross-positional.
- **Pre-registration honoured.** The four decision-surface-only arms (`rb_095/105/115/130`) are
  reported in the ladder and **never value-scored**, even though Amendment 1 made all arms share
  the same 4-slot design and the original reason for the restriction lapsed. Adding them to the
  value comparison after seeing results is exactly what pre-registration exists to prevent; a
  future phase may value-score them prospectively.
- **Data vintage** `d2955868…` throughout, recorded on every row. Not comparable with pre-D109
  published figures (D109 §0: the nflverse panel was restated upstream).
- `ruff check` and `ruff format --check` clean on `src tests`; `models/` `73b408e9` and `league/`
  `d4cfd00e` unchanged; working tree otherwise clean.

## A limitation this phase cannot remove

D110 holds `confidence` frozen, which is what makes `risk` a control rather than a confound — but
it also means the arms measure the **magnitude channel alone**. A genuine recalibration would move
confidence too: under a multiplier *m* with the absolute interval unchanged,
`conf' = 1 − (1 − conf)/m`, so an RB ×1.20 correction would additionally lift RB's risk multiplier
from 0.604 to 0.670 (**+10.9%**, against +6.5% for WR and QB). The arms here therefore *understate*
a real recalibration by roughly 4% in RB-versus-WR relative terms. That is small against the
effects measured, and it does not rescue the null — but it is a reason the eventual risk phase and
any future magnitude work should be run **jointly**, not sequentially.
