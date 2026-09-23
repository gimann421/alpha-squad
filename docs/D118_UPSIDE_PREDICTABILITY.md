# D118 — Is player-specific upside predictable from what Alpha already knows?

**Headline: partly in the statistical sense, and not demonstrated as a draft signal. One piece
of existing information predicts the board projection's error out of sample, in every held-out
season: the market's disagreement with the model.** When the preseason consensus ranks a player
higher at his position than Alpha's projection does, he beats his projection more often
(ρ = **+0.27**, CI [+0.20, +0.33]; AUC **0.74** for beating projection by 100+ points). Age and
experience add a small, stable amount. **But at the decision level the signal is too weak to
resolve.** On same-position pairs among draftable players, re-ordering by projection + predicted
error moves pairwise ordering accuracy from **69.1% to 70.4%**, and the net-correct-flip interval
spans zero. On the D116/D117 sequencing pairs it closes about 40% of the projection gap on average
and flips only **3 of 28** same-position pairs (**~1.5%** of total regret, target). Of the three
pre-registered conditions for "predictable", 1 and 3 hold; 2, decision-level improvement, does not.

**No production change. No draft-engine term changed, no new external data, no hyperparameter
searched. Nothing ships.** `src/alpha_squad/` is byte-identical (tree `55e763e8…`).

---

## 1. Plain-English conclusion

* **The projection's errors are not pure noise.** Roughly 3–5% of their variance is predictable
  out of sample from stored preseason information (OOS R² +0.051 all established players, +0.029
  among ECR ≤ 200). The rest, **≥ 95%**, is not predictable from this information set.
* **Almost all of the predictable part is the market.** M6 already uses preseason ECR as one of
  its four features, yet the *within-position* gap between the market's rank and the model's rank
  still predicts the model's error (ρ +0.23 to +0.33 in every season, 2021–2025, in-season; +0.27
  out of sample). The market's view is under-used, not missing.
* **Stable but small:** younger and less experienced players beat projection slightly more often
  (ρ +0.11 / +0.09 out of sample, same sign in all four held-out seasons).
* **Not predictive:** draft capital, the market's ECR range, prior-season snap share and target
  share, and the rookie model's own `breakout_probability`. Prior PPG, games and opportunity
  predict error *size* (bigger players, bigger errors) but not its direction usefully.
* **It barely changes decisions.** The combined signal flips about 11% of same-position pairs.
  Those flips are right 55% of the time, for about +14 realized points per flip, with a
  season-level CI of [−18, +48] among draftable players. One held-out season (2023) goes the
  wrong way.
* **On the pairs that matter, it points the right way and stops short.** On D116/D117's
  same-position sequencing pairs, the predicted error favours the oracle's player 23 of 28 times.
  That is mostly regression to the mean: the projection *alone*, fed through the same
  walk-forward fit, favours O 25 of 28 times, because O is always the lower-projected player. The
  predicted gap is +26 points against a 67-point projection gap, so it flips only 3.
* **What remains.** Even a *perfect* upside signal (D115's `ORACLE_Y1`, re-run on this vintage)
  recovers only **72.7%** of target regret (74.4% dynasty), so **~27% is a rule residual** no
  information fixes. Of the ~48% sequencing share, the existing signal reaches **~1.5–2.6%**
  (target) and **~3.5–5.9%** (dynasty). The remaining **~45%** of total regret is not reachable
  from Alpha's current information.

**This is a statement about Alpha's current information set, not a claim that projection error is
irreducible.** Information Alpha does not store (depth-chart changes, coaching, injury reports,
camp news) was never tested.

---

## 2. What preseason information Alpha has (inventory)

Every source was checked for pre-season availability before use:

| source | fields used | status |
|---|---|---|
| board projection (`load_season_projections`) | `proj` (M6 point for established players, M7 for rookies) | used |
| `market_snapshot`, `ro` / `redraft-overall`, latest Jul/Aug scrape of S | `ecr_rank`, `ecr_best`, `ecr_worst` | used (page-scoped per D56) |
| `players` | `birth_date` → age at Sep 1 of S; `rookie_season` → experience; `draft_pick` | used |
| `player_season_stats`, season S−1 | games, PPG, (targets + carries) / games | used |
| `player_week_stats` REG weeks of S−1 | mean `offense_snap_pct`, mean `target_share` | used |
| `rookie_predictions` | `breakout_probability` (rookies) | used |
| `dynasty_values` | age, dynasty ECR/value | **EXCLUDED**: its only snapshot is 2026-09-18, after every evaluated season, so it would leak the future |
| `edge_snapshot` | model-vs-market edge | **EXCLUDED**: empty |
| M6 p10/p90/top-N/confidence | — | not separate features: D117 showed they are functions of `proj` |

**Pre-registered features:** 12 for established players (`proj, ecr_rank, ecr_range,
mkt_vs_model, age, experience, draft_pick, prior_games, prior_ppg, prior_opp_pg, prior_snap_pct,
prior_target_share`) and 7 for rookies (`proj, ecr_rank, ecr_range, mkt_vs_model, age,
draft_pick, breakout`). `mkt_vs_model` is the player's within-position projection rank minus his
within-position ECR rank. Every feature is z-scored within (season, position), so nothing can
order players *across* positions.

**Population:** QB/RB/WR/TE with a preseason ECR rank. Established: **1,799** player-seasons
(mean e **+2.9**, SD **62.3**; 19.7% beat projection by 50+; 7.3% by 100+). Rookie: **337**
(mean e +14.6, SD 59.9; 24.0% / 9.2%).

**Method:** strictly walk-forward inside 2021–2025. Season S uses training rows from 2021..S−1
only, so the out-of-sample seasons are **2022–2025** (k = 4, t = 3.182). 2021 appears only in the
labelled in-season descriptive table. One ridge per signal (α = 1.0, fixed, never searched) with
per-position intercepts: one per single feature, plus one COMBINED.

---

## 3. Out-of-sample results — established players

ρ is the within-(season, position) Spearman of the prediction with the target, averaged. The CI
is season-clustered (k = 4). "all 4" means the same sign in every held-out season. "order acc" is
same-position pairwise accuracy at ordering REALIZED points: by projection, then by projection +
predicted error.

### 3.1 All established players (n = 1,442 OOS)

| signal | ρ(e) | CI | all 4 | ρ(\|e\|) | AUC +50 | AUC +100 | OOS R² | flips | flips right | gain / flip |
|---|---|---|---|---|---|---|---|---|---|---|
| **COMBINED** | **+0.265** | [+0.20, +0.33] | Y | +0.307 | 0.632 | **0.708** | **+0.051** | 11.7% | 53.2% | **+8.4** [+1.6, +14.7] |
| **mkt_vs_model** | **+0.271** | [+0.20, +0.34] | Y | +0.027 | **0.651** | **0.738** | +0.051 | 11.7% | 53.2% | +7.7 [−2.0, +16.8] |
| age | +0.110 | [+0.03, +0.19] | Y | −0.032 | 0.538 | 0.596 | 0.000 | 4.7% | 53.0% | +5.3 |
| prior_ppg | +0.103 | [+0.07, +0.13] | Y | +0.284 | 0.449 | 0.391 | −0.007 | 0.8% | 55.1% | +3.8 |
| proj (regression to mean) | +0.099 | [+0.02, +0.17] | Y | +0.328 | 0.430 | 0.378 | −0.007 | 0.0% | — | — |
| experience | +0.093 | [+0.00, +0.18] | Y | −0.007 | 0.511 | 0.559 | −0.004 | 4.4% | 52.6% | +4.3 |
| prior_opp_pg | +0.081 | [+0.05, +0.11] | Y | +0.273 | 0.434 | 0.377 | −0.010 | 0.8% | 54.9% | +2.9 |
| prior_games | +0.072 | [−0.01, +0.15] | Y | +0.181 | 0.465 | 0.457 | −0.006 | 2.2% | 49.1% | −1.9 |
| prior_snap_pct | +0.042 | [−0.02, +0.10] | n | +0.237 | 0.423 | 0.398 | −0.013 | 2.3% | 51.2% | +1.2 |
| ecr_range | +0.033 | [−0.06, +0.12] | n | −0.098 | 0.510 | 0.542 | −0.012 | 0.9% | 45.2% | −6.3 |
| prior_target_share | +0.032 | [−0.03, +0.09] | n | +0.218 | 0.422 | 0.370 | −0.014 | 0.7% | 49.5% | −5.6 |
| draft_pick | +0.013 | [−0.10, +0.12] | n | +0.201 | 0.589 | 0.640 | −0.011 | 0.8% | 51.3% | −0.4 |
| ecr_rank | +0.003 | [−0.06, +0.07] | n | +0.319 | 0.618 | 0.702 | −0.011 | 0.5% | 67.2% | +30.0 |

Pairwise ordering accuracy, projection → COMBINED: **76.7% → 77.5%**.

### 3.2 Decision slice — ECR ≤ 200 (n = 633 OOS)

| signal | ρ(e) | CI | all 4 | AUC +100 | order acc proj → adj | net correct flips / season | gain / flip |
|---|---|---|---|---|---|---|---|
| **COMBINED** | **+0.230** | [+0.11, +0.35] | Y | 0.698 | **69.1% → 70.4%** | +46.8, CI **[−44, +138]** | +14.1, CI [−17.6, +48.5] |
| **mkt_vs_model** | **+0.222** | [+0.06, +0.38] | Y | 0.726 | 69.1% → 70.0% | +32.5, CI [−33, +98] | +12.6, CI [−17.0, +45.3] |
| age | +0.075 | [−0.01, +0.16] | Y | 0.639 | 69.1% → 69.7% | +22.0, CI [−5, +49] | +14.9 |
| experience | +0.036 | [−0.02, +0.09] | n | 0.606 | 69.1% → 69.6% | +20.0 | +12.4 |
| every other single feature | \|ρ\| ≤ 0.12, CI spans 0 | | | | ≤ +0.1pp | CI spans 0 | |

The COMBINED model's net correct flips by season are **+77, −38, +63, +85**. The signal is right
on balance in three seasons and wrong in 2023. By position (ECR ≤ 200, COMBINED ρ):
**QB +0.30, WR +0.28, TE +0.23, RB +0.11**. RB, the largest regret source, is the weakest.

### 3.3 Sign stability across all five seasons (descriptive, in-season, NOT out of sample)

| feature | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| **mkt_vs_model** | **+0.33** | **+0.32** | **+0.30** | **+0.25** | **+0.23** |
| age | −0.15 | −0.11 | −0.18 | −0.07 | −0.08 |
| experience | −0.13 | −0.12 | −0.16 | −0.04 | −0.05 |
| proj | −0.09 | −0.16 | −0.09 | −0.04 | −0.10 |
| prior_ppg | −0.08 | −0.10 | −0.12 | −0.08 | −0.11 |
| draft_pick, ecr_range, ecr_rank, prior_target_share | mixed signs | | | | |

The market-disagreement signal survives all five seasons and is not driven by any one of them,
though it is **declining** (+0.33 in 2021 → +0.23 in 2025).

### 3.4 Rookies (secondary; n = 272 OOS, 83 at ECR ≤ 200)

| signal | ρ(e) | CI | AUC +100 | order acc proj → adj | net correct flips / season | gain / flip |
|---|---|---|---|---|---|---|
| **COMBINED** (all) | **+0.394** | [+0.26, +0.53] | 0.862 | **70.7% → 74.3%** | **+25.0, CI [+11, +39]** | **+20.3** [+4.9, +36.8] |
| mkt_vs_model (all) | +0.407 | [+0.33, +0.49] | 0.818 | 70.7% → 74.3% | +25.0, CI [+3, +47] | +16.3 |
| ecr_rank (all) | +0.153 | [−0.03, +0.34] | 0.693 | 70.7% → 73.5% | +19.8, CI [+11, +28] | +40.2 [+19, +58] |
| COMBINED (ECR ≤ 200) | +0.403 | [+0.13, +0.68] | 0.712 | 68.8% → 70.4% | +1.2, CI [−6, +9] | +9.4 |
| breakout_probability (all) | −0.077 | [−0.31, +0.15] | 0.459 | ≈ 0 | CI spans 0 | — |

**For rookies the market clearly out-knows M7.** On the whole rookie board all three decision
conditions hold. In the draftable slice (n = 83) the effect is unresolved. The rookie model's own
`breakout_probability` carries nothing.

---

## 4. Same-position pairs on the D116/D117 sequencing population

These are D117's measured C1 ∧ C2 pairs, on the same vintage (checked). The oracle's identity is
never a feature. Trained signals exist for 2022–2025 only. K/DST players and 2021 pairs are
counted as undefined.

| signal | target: same-pos defined | favours O | **flips to O** | regret flipped | dynasty: defined / favours O / flips | regret flipped |
|---|---|---|---|---|---|---|
| **COMBINED** | 28 | 23 | **3** | 0.9% | 25 / 25 / **8** | 2.2% |
| **mkt_vs_model** | 28 | 23 | **4** | 1.4% | 25 / 22 / 1 | 0.4% |
| age | 28 | 19 | 1 | 0.2% | 25 / 18 / 0 | 0 |
| proj (the regression-to-mean baseline) | 28 | **25** | 0 | 0 | 25 / 25 / 0 | 0 |
| ecr_rank | 28 | 9 | 0 | 0 | 25 / 16 / 0 | 0 |
| every other feature | ≤ 28 | 6–17 | 0 | 0 | | 0 |

* **"Favours O" is not the test.** O is the lower-projected player on every same-position pair,
  so *any* regression-to-the-mean signal favours him. The projection's own walk-forward fit
  favours O 25 of 28 times, *more* than the combined model. Chance is not 50% on this population.
* **The flip is the test,** and it rarely happens. Mean predicted-error gap O − A: **+26.2**
  (COMBINED) and +28.0 (mkt_vs_model), against a projection gap A − O of **+66.6** in target.
  Dynasty: +35.3 against +60.0.
* **Cross-position pairs** (secondary, replacement-level scale): COMBINED flips 2 of 51 (0.6%)
  target and 13 of 63 (3.7%) dynasty.

---

## 5. Is any signal strong enough to plausibly improve draft decisions?

Against the verdict rule fixed in the runner before any result existed (established cohort):

| condition | COMBINED | mkt_vs_model | met? |
|---|---|---|---|
| 1. OOS ρ CI excludes 0 and same sign in all 4 seasons | +0.230 [+0.11, +0.35], all 4 | +0.222 [+0.06, +0.38], all 4 | **yes** |
| 2. net correct same-position flips, CI excluding 0 (ECR ≤ 200) | +46.8 [−44, +138] | +32.5 [−33, +98] | **no** |
| 3. flips ≥ 5% of close ECR ≤ 200 same-position pairs | 30.6% | 26.0% | **yes** |

**Verdict: player-specific upside is not demonstrated as a usable draft signal from Alpha's
current information set.** A genuine predictive signal exists: the market's within-position
disagreement with the projection, stable in every season. Its decision-level payoff is about 1
percentage point of pairwise ordering accuracy, with an interval that includes zero. **No
production change is justified.** D111 (on an unmerged branch, not on main) reached the
consistent result for a rank-consensus blend of Y1 and ECR: positive but below its detection
floor.

---

## 6. How much of D115's regret could this address?

Share of **total** per-format regret on this vintage (target 44,027; dynasty 42,218):

| | target | dynasty |
|---|---|---|
| sequencing population (C1 ∧ C2, D116) | 48.1% | 46.5% |
| **perfect upside signal** (D115 `ORACLE_Y1`, re-run here) | **72.7%** of *all* regret | **74.4%** |
| → regret remaining even under a perfect signal (rule residual) | **~27%** | **~26%** |
| sequencing pairs flipped toward O by COMBINED (same + cross position) | **1.5%** | **5.9%** |
| …by mkt_vs_model | 2.6% | 3.5% |
| context: existing preseason arms (D115, this vintage): FP_ECR / X2 / X3 mean one-step delta | +1.6 / +0.9 / +1.2 pts/pick | +3.0 / +2.2 / +1.7 |

The 1.5–5.9% is an **upper bound**. It counts flips on a hindsight-selected set where O is always
the right answer. On the general population the same flips are right only 53–56% of the time, so
the net effect of acting on the signal everywhere would be smaller.

---

## 7. What remains unexplained

* **≥ 95% of the projection's out-of-sample error variance** (OOS R² ≤ 0.051) is not predicted by
  any stored preseason information.
* D117's finding stands: oracle players beat their *own* p90 in ~90% of cases. D118 adds that the
  stored preseason information ranks them only modestly higher than their projection does.
* **~45 points of the ~48% sequencing share** (target) are not reachable by any signal Alpha
  currently holds.
* **~27% of total regret** is a rule residual that even perfect projections do not recover
  (`ORACLE_Y1`). It is not an information problem at all.
* **Not tested, because Alpha does not store it:** in-preseason news (depth charts, injuries,
  coaching or scheme changes, camp reports), team-level offensive changes, and target competition.
  The negative result is about this information set only.

---

## 8. Recommended next research question (exactly one)

> **Would a pre-registered, walk-forward market-disagreement correction to the board projection
> (proj + ê from `mkt_vs_model`, fitted on prior seasons only, specification frozen from D118)
> change enough picks, correctly enough, to be detectable above D114's one-step MDE (~13
> points/pick)? Answer it first as an expected-effect power calculation from D118's measured flip
> rate, flip accuracy and gain per flip, and run the one-step controlled test on the D115 grid
> ONLY if that calculation clears the MDE.**

It is the only signal that met the out-of-sample condition, and the brief asks what controlled
experiment should test a signal that exists. The power-first gate is the lesson of D111/D114:
running an arm whose expected effect sits below the instrument's floor produces an uninterpretable
null. The rookie cohort, where the decision-level conditions hold on the whole board, is the place
the effect would be largest. If the power check fails, close the line: the market-disagreement
signal is real but too small for this instrument.

---

## 9. Reproducibility, provenance and what changed

```bash
uv run python scripts/research/d115_regret_attribution.py --mode arms --leagues target_league --out <t>
uv run python scripts/research/d115_regret_attribution.py --mode arms --leagues dynasty_1qb   --out <d>
uv run python scripts/research/d118_upside_predictability.py --mode measure --d117 <d117 out> --out <o>
uv run python scripts/research/d118_upside_predictability.py --mode report  --out <o> \
    --arms <t>/d115_arms.json --arms <d>/d115_arms.json
uv run pytest tests/unit/test_d118_upside_predictability.py
```

| item | value |
|---|---|
| HEAD at run time | `b7a0a27eed405dd02b60caf32156e268c5883140` (D117) |
| `src/alpha_squad` tree / dirty | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` / **False** |
| board vintage | `f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f` (= D116/D117; the runner refuses a mismatch) |
| per season | 2021 `79599ffa…` 2022 `43f0e968…` 2023 `aa73cd3f…` 2024 `7873284c…` 2025 `0b344c7e…` |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| models | `uncertainty_catboost_v2` (M6), `rookie_features_v1` (M7) |
| input `d117_measured.json` sha256 | `e1d332d99dd9baec5a8c6dc0b691b4d5be31a2ef816e42d79e6d2a82a19dab5d` |
| D115 arms on this vintage (target / dynasty) sha256 | `b259beba…` / `72c5d74c…` |
| D118 `d118_measured.json` / `d118_summary.json` sha256 | `35bffd00…` / `7e9edf90…` |

**Files changed by D118 — research only:**

| file | status |
|---|---|
| `scripts/research/d118_upside_predictability.py` | **new**: measure / report runner |
| `tests/unit/test_d118_upside_predictability.py` | **new**: 23 tests |
| `docs/D118_UPSIDE_PREDICTABILITY.md` | **new**: this report |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged** |
