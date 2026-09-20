# W3 — What the existing Alpha weekly model can already do

**Status: COMPLETE.** Run exactly as pre-registered in `docs/weekly/W3_PREREGISTRATION.md`,
which was committed before any Alpha ranking metric existed. **No model was built, tuned,
retrained selectively or modified. No ECR entered Alpha. No production file changed.**

Provenance: Alpha `ml_catboost` at commit `12aa1f5`, trained by the unmodified
`alpha-squad train established --season-start 2021 --season-end 2025 --min-train-season 2015`;
ECR vintage `e270d790…5db9a5` (identical to W1/W2); 79 weeks, 2021–2025, Full PPR, Friday
cutoff. Results: `reports/weekly/w3_results.json`.

---

## 1. Headline

**Alpha contains real weekly ranking signal, it is roughly half of ECR's, and it is almost
entirely in the body and tail of the board rather than at the top.**

FLEX, 79 weeks, versus the season-to-date baseline:

| | Alpha − baseline | ECR − baseline | Alpha's share |
|---|---:|---:|---:|
| **Spearman ρ** | **+0.0347** (2.4× MDE, 68–11 weeks, p = 3e-12) | +0.0660 | **53%** |
| **points captured @10** | **+0.0027** (0.16× MDE, 39–40 weeks, p = 0.78) | +0.0415 | **7%** |

Those two rows are the phase. Alpha's overall ordering advantage over the obvious baseline is
large, consistent and statistically overwhelming — it wins 68 of 79 weeks. **Its top-10
advantage is exactly zero**: 39 weeks better, 40 weeks worse, an effect six times smaller than
what 79 weeks can resolve.

**Alpha loses to ECR on every board and every metric**, by −0.031 Spearman on FLEX (5.2× MDE,
8–71 weeks). There is no metric, depth or position at which Alpha is ahead.

---

## 2. What Alpha actually is

Audited against the repo before any result was computed. W1's sketch was right and incomplete.

| | |
|---|---|
| model | **`ml_catboost`** — `CatBoostRegressor(iterations=200, depth=4, learning_rate=0.05, loss_function="MAE", random_seed=42)` |
| why this one | it is `WEEKLY_PROJECTION_BASE_MODEL`, the **only** model whose weekly predictions are persisted, and therefore the only one `/rankings/weekly` can serve. The same training run also fits ridge, xgboost, two ablations and an ensemble — all produce **season totals only** and are not weekly ranking systems |
| features | **11**: `games_played_prior`, `fp_ppr_avg_last3`, `fp_ppr_avg_season_to_date`, `targets/carries/receptions/target_share/snap_pct _avg_last3`, `team_plays/pass_rate/epa _avg_last3` |
| not present | **no opponent, no matchup, no injury, no depth chart, no Vegas, no weather, no rest, no ECR** |
| positions | **QB, RB, WR, TE.** No K, no DST — not retrofitted |
| target | `target_fantasy_points_ppr` — Full PPR only |
| training | per position, walk-forward expanding window, seasons `[2015, S−1]` |
| ranking | none existed; W3 ranks by predicted points, ties by `player_id` |
| FLEX | none existed; W3 pools RB + WR + TE predictions and ranks by predicted points, **no separate model, no normalisation, no manual adjustment** |

### 2.1 Two limitations that are findings, not footnotes

**(a) The current Alpha weekly model cannot produce a real Friday board.**
`player_week_features` is built from `player_week_stats`, which has a row for a player-week
**only if the player appeared in that game**. So Alpha can only emit a prediction for someone
who played — which on Friday it cannot know. It scores retrospectively.

This does not contaminate W3: every system is evaluated on the same evaluable set (ranked
players who played), exactly as W2 defined it, and neither Alpha nor ECR is being asked to
predict availability. But **as a product, the weekly model is not deployable in its current
form.** Building a feature row for every *rostered* player is infrastructure that does not
exist.

**(b) The served product's evidence layer was excluded on leakage grounds.**
`/rankings/weekly` serves the base prediction adjusted by `projection_deltas` (M9, bounded
±15%). That layer's `detect_injury_events` reads the nflverse injury file with `WHERE i.week = ?`
and **no `date_modified` filter**. nflverse stores one *final* row per player-week; measured
across 2021–2024, **7.2%–9.8% of the `Out`/`Doubtful` rows it consumes were last modified after
Friday**, and the **2025 file has no `date_modified` column at all**, so it cannot be filtered
even in principle. The W3 brief forbids post-cutoff injury information outright, so the layer
is out. **This is a live leakage defect in the served product path** and is the first W4
candidate in §10.

---

## 3. Leakage and data audit

| check | result |
|---|---|
| ECR reachable by Alpha? | **No.** No feature name is market-derived, *and* `player_week_features` physically contains only the 11 features + target + identity — there is nothing else to read |
| features from strictly earlier games? | **PASS** — 0 rows claim prior games with no strictly-earlier `game_date` on record |
| training window | strictly `season < target_season`; 2021 predictions required the 2015–2020 ingest, which was added for this reason |
| already-played players evaluated? | **0**, across all 79 weeks (W2's rule, re-applied) |
| Vegas / weather / closing lines | absent from the feature set entirely |
| post-cutoff injury | excluded with the evidence layer (§2.1b) |
| Friday cutoff defensible? | **Yes for Alpha's features** — every one is a lag over completed games, so a Friday cutoff is if anything *conservative*: those games all finished days earlier |

**One feature-semantics note, not a defect.** `fp_ppr_avg_last3` is partitioned by player only
(not by player-season), so a player's "last 3 games" can span a season boundary. That is
deliberate and leakage-safe — the games are strictly earlier — but it means a week-1 row can
carry last season's form.

**Coverage.** Alpha ranks **98.2%** of the shared universe (min 88.0%); FLEX 98.3%, RB lowest at
95.2%. The gap is a clean taxonomy mismatch: the unrankable players are **fullbacks**.
FantasyPros lists FB under RB; nflverse types them `FB`, which is not in the model's
`POSITIONS`, so they are never trained on or predicted. ~4.6 FLEX players per week. Reported,
not imputed.

---

## 4. The three systems

Per-week means, 79 weeks, Full PPR. All systems ranked the identical player set each week.

| board | system | ρ | SD | pairwise | decisive | prec@10 | cap@10 | cap@25 | cap@50 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **FLEX** | ECR | **0.679** | 0.042 | 0.752 | 0.810 | 0.260 | 0.637 | 0.689 | 0.760 |
| | **Alpha** | **0.648** | 0.050 | 0.738 | 0.794 | 0.219 | 0.598 | 0.662 | 0.737 |
| | baseline B0 | 0.613 | 0.096 | 0.724 | 0.778 | 0.222 | 0.595 | 0.650 | 0.719 |
| | prior-season B1 | 0.442 | 0.055 | 0.659 | 0.699 | 0.206 | 0.574 | 0.648 | 0.691 |
| **QB** | ECR | 0.491 | 0.153 | 0.677 | 0.711 | 0.551 | 0.809 | 0.944 | — |
| | Alpha | 0.416 | 0.174 | 0.649 | 0.679 | 0.498 | 0.767 | 0.935 | — |
| | B0 | 0.392 | 0.198 | 0.641 | 0.666 | 0.509 | 0.768 | 0.930 | — |
| **RB** | ECR | 0.705 | 0.070 | 0.761 | 0.817 | 0.433 | 0.713 | 0.832 | 0.931 |
| | Alpha | 0.668 | 0.080 | 0.744 | 0.799 | 0.392 | 0.690 | 0.807 | 0.921 |
| | B0 | 0.641 | 0.120 | 0.734 | 0.785 | 0.382 | 0.670 | 0.798 | 0.912 |
| **WR** | ECR | 0.666 | 0.062 | 0.748 | 0.800 | 0.349 | 0.673 | 0.759 | 0.842 |
| | Alpha | 0.636 | 0.064 | 0.735 | 0.784 | 0.313 | 0.641 | 0.732 | 0.828 |
| | B0 | 0.601 | 0.097 | 0.721 | 0.769 | 0.311 | 0.634 | 0.719 | 0.813 |
| **TE** | ECR | 0.611 | 0.102 | 0.728 | 0.796 | 0.484 | 0.722 | 0.836 | 0.951 |
| | Alpha | 0.576 | 0.104 | 0.713 | 0.778 | 0.456 | 0.696 | 0.821 | 0.949 |
| | B0 | 0.525 | 0.147 | 0.693 | 0.753 | 0.432 | 0.661 | 0.795 | 0.940 |

**The ordering is identical on every board: ECR > Alpha > B0 > B1.** Alpha sits between the
trivial baseline and the expert consensus, everywhere, without exception.

**One property in Alpha's favour that no comparison metric shows:** Alpha's week-to-week SD is
far lower than the baseline's (FLEX 0.050 vs 0.096; RB 0.080 vs 0.120; TE 0.104 vs 0.147).
Alpha is a **more stable** ranker than season-to-date averaging — closer to ECR's stability
(0.042) than to the baseline's. A model that is reliably mediocre is a better foundation than
one that is erratically average.

---

## 5. The three pre-registered comparisons

### 5.1 Alpha vs the season-to-date baseline — **real signal, but only away from the top**

FLEX, paired within week:

| metric | mean | 95% CI | × MDE | W–L–T | Wilcoxon p | effect (rb) |
|---|---:|---|---:|---:|---:|---:|
| Spearman | **+0.0347** | [+0.0233, +0.0523] | 2.39 | **68–11–0** | 2.9e-12 | +0.90 |
| pairwise | +0.0139 | [+0.0096, +0.0202] | 2.64 | 70–9–0 | 1.4e-12 | +0.92 |
| decisive-pair | +0.0160 | [+0.0108, +0.0241] | 2.41 | 69–10–0 | 3.2e-12 | +0.90 |
| capture@50 | +0.0186 | [+0.0094, +0.0314] | 1.69 | 53–26–0 | 3.3e-05 | +0.54 |
| capture@25 | +0.0118 | [−0.0016, +0.0273] | 0.82 | 45–34–0 | 0.195 | +0.17 |
| **capture@10** | **+0.0027** | **[−0.0138, +0.0196]** | **0.16** | **39–40–0** | **0.777** | −0.04 |
| **precision@10** | **−0.0025** | [−0.0218, +0.0167] | 0.13 | 20–23–36 | 0.649 | −0.08 |

Overwhelming on overall ordering; **nothing at all at the top 10**. The gradient is monotone:
the deeper the depth, the bigger Alpha's edge (capture@50 1.69× → @25 0.82× → @10 0.16×).

By position, Alpha's Spearman edge over the baseline is resolvable everywhere —
TE **+0.0509** (2.37×), WR +0.0351 (2.47×), RB +0.0269 (1.79×) — except **QB +0.0248 (1.24×,
47–32 weeks, p = 0.04)**, which is Alpha's weakest board and barely clears the noise floor.

### 5.2 ECR vs the baseline — **W2 reproduced exactly**

FLEX Spearman **+0.0660** [+0.0512, +0.0880], 77–2 weeks. W2 reported **+0.066** on its own
universe. The W3 re-run, on a slightly smaller Alpha-restricted universe, reproduces it to
three decimals. That is a strong reproducibility check on the whole instrument, and it means
the +0.066 figure can be used as the reference scale without caveat.

### 5.3 Alpha vs ECR — **Alpha loses everywhere**

FLEX:

| metric | mean | 95% CI | × MDE | W–L–T | p |
|---|---:|---|---:|---:|---:|
| Spearman | −0.0313 | [−0.0377, −0.0256] | **5.15** | 8–71–0 | 3.7e-13 |
| pairwise | −0.0136 | [−0.0162, −0.0112] | 5.35 | 4–75–0 | 2.2e-13 |
| decisive-pair | −0.0160 | [−0.0189, −0.0132] | 5.65 | 6–73–0 | 2.5e-13 |
| capture@10 | −0.0388 | [−0.0550, −0.0226] | 2.39 | 21–58–0 | 4.5e-05 |
| capture@50 | −0.0225 | [−0.0290, −0.0162] | 3.51 | 16–62–1 | 1.3e-08 |

Same direction on QB, RB, WR and TE. The deficit is remarkably uniform: −0.031 (FLEX), −0.075
(QB), −0.038 (RB), −0.031 (WR), −0.034 (TE) Spearman.

### 5.4 Alpha's share of ECR's edge, by board and depth

| board | Spearman share | capture@10 share |
|---|---:|---:|
| FLEX | **53%** | **7%** |
| TE | 60% | 57% |
| WR | 54% | 18% |
| RB | 42% | 46% |
| QB | 25% | −3% |

---

## 6. Results by depth — the central finding

Alpha's edge over the baseline, in MDE units, by depth (FLEX):

    full board (ρ)   2.39   ####################
    capture@50       1.69   ##############
    capture@25       0.82   #######
    capture@10       0.16   #

**Alpha's signal is a deep-board signal.** It orders the middle and tail of the FLEX pool
materially better than season-to-date averaging and contributes nothing at the top 10 — which
is precisely where W2 found the largest absolute headroom (ECR's own precision@10 is only
0.260) and precisely where a FLEX start/sit decision is made.

---

## 7. Cross-position / FLEX findings

This is where the top-10 collapse comes from, and the answer needed two measurements that point
in different directions. Both are reported.

### 7.1 The pooling loses most of the positional top-10 signal

Alpha's capture@10 edge over the baseline, measured on each **positional** board, versus the
**pooled** FLEX board:

| board | Alpha − B0, capture@10 |
|---|---:|
| RB | +0.0198 |
| WR | +0.0070 |
| TE | +0.0346 |
| **pooled FLEX** | **+0.0027** |

Weighting the positional edges by their share of the FLEX pool (RB 29.5%, WR 46.9%, TE 23.6%)
predicts a pooled edge of about **+0.017**. The observed value is **+0.0027** — roughly
**84% of the positional top-10 signal is destroyed by pooling.**

### 7.2 The composition shows the mechanism: TE is crushed, RB is inflated

Share of the FLEX **top-10** filled by each position, against the realized top-10:

| system | RB pred | RB real | WR pred | WR real | **TE pred** | **TE real** |
|---|---:|---:|---:|---:|---:|---:|
| **Alpha** | **0.534** | 0.381 | 0.452 | 0.511 | **0.014** | 0.108 |
| ECR | 0.458 | 0.381 | 0.496 | 0.511 | 0.046 | 0.108 |
| baseline | 0.441 | 0.381 | 0.513 | 0.511 | 0.047 | 0.108 |

**Alpha's FLEX top-10 is 1.4% tight end** — against a realized 10.8% and a pool share of 23.6%.
It is effectively a TE-free board. It over-represents RB by **+15.3 points** against realized,
double ECR's +7.7 and the baseline's +6.0. All three systems under-rate TE at the top; Alpha
does so about three times as severely.

This is consistent with the relative point bias: Alpha under-predicts RB by −15.1%, WR by
−15.4% and **TE by −19.7%**. Three separately-fit models with different relative scales, pooled
without normalisation, put the shortest-scaled position last.

### 7.3 But cross-position calibration is **not** the main story for overall ordering

Decomposing the FLEX board's Spearman into within-position and pooled:

| system | pooled ρ | RB within | WR within | TE within | mean within |
|---|---:|---:|---:|---:|---:|
| Alpha | 0.6479 | 0.6717 | 0.6425 | 0.5825 | 0.6322 |
| ECR | 0.6792 | 0.7110 | 0.6729 | 0.6171 | 0.6670 |

Alpha's deficit to ECR **within** positions is **−0.0348**; its deficit **pooled** is **−0.0313**.
They are the same size. Pooling slightly *helps* both systems (+0.016 Alpha, +0.012 ECR).

**So the honest conclusion is two-sided, and it would have been easy to get wrong:**
cross-position miscalibration is a **top-of-FLEX** problem — severe there, worth 84% of the
positional top-10 signal — and is **not** the driver of Alpha's overall ranking deficit. Alpha
is simply worse than ECR inside every position by about the same margin as it is pooled. A
composition table alone would have suggested calibration explains everything; the decomposition
shows it does not.

---

## 8. Point-prediction diagnostics — **SECONDARY**

Not a success criterion. Reported because the relationship is itself informative.

| board | n/week | MAE | RMSE | mean signed bias |
|---|---:|---:|---:|---:|
| FLEX | 257.8 | 4.183 | 6.096 | **−1.203** |
| QB | 29.9 | 6.172 | 7.745 | −0.252 |
| RB | 75.1 | 4.506 | 6.480 | −1.274 |
| WR | 118.7 | 4.424 | 6.332 | −1.212 |
| TE | 60.0 | 3.478 | 5.074 | −1.170 |

**Alpha under-predicts nearly uniformly.** Decile calibration (FLEX):

| decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| predicted | 0.37 | 1.44 | 2.24 | 3.08 | 4.22 | 5.67 | 7.37 | 9.34 | 11.58 | 14.55 |
| realized | 1.46 | 2.48 | 3.34 | 4.27 | 5.19 | 6.96 | 8.72 | 10.59 | 13.00 | 15.87 |
| gap | −1.09 | −1.03 | −1.10 | −1.19 | −0.96 | −1.30 | −1.35 | −1.25 | −1.43 | −1.32 |

The gap is **almost constant** (−0.96 to −1.43) across the whole range. A constant additive
shift **cannot change a ranking at all**. So the visible "Alpha is biased low" effect is
essentially irrelevant to the primary objective — and "fixing" it would buy nothing. This is
exactly the trap the brief warned about, made concrete: it is the most obvious-looking defect
in the diagnostics and it is the one least worth acting on.

What *does* matter is the *relative* bias differing by position (§7.2), because on a pooled
board that reorders.

**Do point accuracy and ranking quality move together?** Yes: across 79 weeks,
`corr(weekly MAE, weekly Spearman) = −0.685`. Weeks Alpha projects accurately are weeks it
orders well. But that is a within-system correlation across weeks, **not** evidence that
reducing MAE would improve ranking — the flat calibration curve above is the counterexample.

---

## 9. Season variation and scope

FLEX Spearman by season:

| season | weeks | Alpha | ECR | B0 | Alpha−B0 | ECR−B0 | Alpha−ECR |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 17 | 0.621 | 0.657 | 0.563 | +0.059 | +0.095 | −0.036 |
| 2022 | 16 | 0.618 | 0.650 | 0.587 | +0.031 | +0.063 | −0.032 |
| 2023 | 16 | 0.661 | 0.694 | 0.629 | +0.033 | +0.065 | −0.032 |
| 2024 | 14 | 0.671 | 0.697 | 0.657 | +0.015 | +0.041 | −0.026 |
| 2025 | 16 | 0.672 | 0.701 | 0.640 | +0.033 | +0.062 | −0.029 |

Alpha's deficit to ECR is **stable** (−0.026 to −0.036). Its edge over the baseline varies more
(+0.015 to +0.059) and is smallest in 2024 — the season where the baseline itself is strongest.

**Scope unchanged from W2:** 79 weeks, the same 11 exclusions, all missing-ECR. **Zero invalid
cells.** Week 1 is absent in four of five seasons, so — as in W2 — everything here describes
performance *conditional on in-season data existing*. That caveat bites harder for Alpha than
for ECR: 8 of Alpha's 11 features are current-season lags.

---

## 10. What this means for the product

**Where Alpha produces useful signal**
- **Deep-board ordering.** +0.035 Spearman over the baseline on FLEX, 68 of 79 weeks — a real,
  large, reliable effect. For waiver research, bench decisions and deep leagues, Alpha is
  already meaningfully better than the obvious alternative.
- **Stability.** Materially lower week-to-week variance than the baseline, close to ECR's.
- **TE.** Its best position relative to ECR (60% of the Spearman edge, 57% of the capture@10
  edge) — the position where expert consensus is weakest.

**Where it does not**
- **The top of the FLEX board.** Zero measurable edge over a season-to-date average at top 10.
  This is the single most product-relevant depth and Alpha currently adds nothing there.
- **QB.** 25% of ECR's edge, barely above the noise floor.
- **As a shippable product at all** — it cannot produce a Friday board (§2.1a).

**Is it competitive with ECR?** No. Not on any board, metric or depth, and the FLEX deficit
(5.2× MDE, 8–71 weeks) is far outside what 79 weeks could mistake for noise. **Alpha does not
currently justify replacing ECR**, and W2's practical product gate is not met.

**Is the gap large enough to justify further research?** Yes, and for a specific reason: Alpha
recovers ~53% of ECR's overall edge using **11 features, none of which is opponent, injury,
matchup or news**. ECR's experts have all of those. That a lag-only model gets half way there
suggests the remaining half is information, not architecture — and the information gap is
nameable rather than mysterious.

---

## 11. Recommended W4

### The question

> **Why does Alpha's per-position top-10 signal disappear when the three models are pooled into
> a FLEX board — and can it be recovered by cross-position calibration alone, with no new
> features and no new data?**

### Does this advance the north-star goal?

Yes, directly and narrowly. The north star is the best possible weekly expected-point ranking,
and FLEX is the ranking users act on. W2 established that the top of the FLEX board is where the
largest absolute headroom sits. W3 has now established that Alpha *already has* top-10 signal at
the positional level (RB +0.020, TE +0.035 capture@10 over baseline) and **loses ~84% of it in
the pooling step**. That is not a hypothetical improvement — it is measured signal currently
being thrown away by a step that involves no modelling at all.

### Why this rather than the obvious alternatives

- **Not feature engineering.** Adding opponent/injury/Vegas features is the intuitive next move
  and is probably where the *other* half of the ECR gap lives. But it is expensive, it needs new
  point-in-time infrastructure (W1 §6.5 ruled Vegas and weather unusable historically), and it
  would be added on top of a pooling step that demonstrably destroys signal. Fix the leak before
  pouring more in.
- **Not adding ECR.** That is System C in the eventual design and it is premature: until we know
  how much of Alpha's gap is recoverable without ECR, adding it confounds "Alpha improved" with
  "Alpha imported the benchmark".
- **Not reducing MAE.** §8 is the counterexample — the calibration curve is flat, so the
  headline point-error defect cannot change any ranking.
- **Not K/DST.** The model does not produce them, ECR is near-noise there (W2: K ρ = 0.127), and
  they are 2 of 10 starting slots.

### What W4 should do concretely

Measure, under pre-registration, whether a cross-position transformation fitted **only on
strictly-prior seasons** (so it stays Friday-safe and out-of-sample) recovers the pooled
top-10 signal: per-position calibration of predicted-to-realized scale, evaluated at FLEX
top-10/25/50 against this phase's numbers as the frozen baseline. The decision rule should be
fixed in advance against W3's measured MDEs (capture@10 ±0.017, Spearman ±0.015).

**Two W4 candidates that should be scheduled alongside but not conflated with it:**
1. **Fix the evidence layer's injury cutoff** (§2.1b) — a live leakage defect in the *served*
   product path, independent of any research question.
2. **Make Alpha able to produce a Friday board** (§2.1a) — the blocking product limitation.
   Neither is a ranking-quality experiment; both are prerequisites for shipping anything.

---

## 12. Reproducing

```bash
uv run alpha-squad sources ingest --season-start 2015 --season-end 2025
uv run alpha-squad identity build
uv run alpha-squad features build --season-start 2015 --season-end 2025
uv run alpha-squad train established --season-start 2021 --season-end 2025 --min-train-season 2015
uv run python scripts/research/w3_alpha_benchmark.py --out reports/weekly/w3_results.json
uv run pytest tests/unit/test_weekly_*.py tests/leakage/
```

Two independent runs of the benchmark are **byte-identical** (`cells`, `summary`, `coverage`,
`flex_composition`). 1521 tests pass, 44 deselected. `make lint` clean, both halves. Diff
against `models/`, `league/`, `api/`, `cli.py`, `features/`, `sources/`, `evidence/`,
`market/`, `uv.lock` and the Makefile is **empty**.
