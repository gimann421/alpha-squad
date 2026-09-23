# D119 — Can a one-step experiment detect D118's market-vs-model correction? Power analysis: NO-GO.

**Headline: NO-GO. The experiment was not run.** The frozen treatment is D118's market-vs-model
correction, fully specified with nothing to tune. Under the pre-registered conservative
assumptions, the one-step matched-state experiment has **8% power** to detect the smallest effect
worth detecting (**3.6 points per pick**) in the primary format. Its 80%-power MDE is **21.2
points/pick**. The signal's realistic expected effect is **~1–3 points/pick**, so the experiment
could not tell "about zero" from "a practically meaningful small improvement" on any plausible
input. The NO-GO survives every GO-favourable assumption the analysis allows, including ignoring
season clustering. **This research line is closed for now.**

**No production change. Nothing tuned, nothing run beyond the power calculation. Nothing ships.**
`src/alpha_squad/` byte-identical (tree `55e763e8…`).

---

## 1. Plain-English power conclusion

The correction would change about a quarter of Alpha's picks. D118 measured those changes as
right only **55%** of the time, for about **+12.6 raw points per change**, with a season CI of
[−17, +45]. Spread across every pick, that is an expected **+3.3 points/pick** at most, and
**+1.1** if the correction touches fewer picks.

Meanwhile a single changed pick's one-step roster outcome has an SD of **~64–71 points**, the
effective sample is **four seasons** (2021 has no walk-forward correction), and with 3 degrees of
freedom the 95% critical value is **3.18**. The design can reliably see effects of ~11–21
points/pick (80% power). It cannot see 1–4.

Running the experiment would produce an interval roughly ±16 points wide around a true effect of
~3. Whatever the point estimate, that result could not support any conclusion, which is exactly
the outcome D111/D114 warned against.

---

## 2. The frozen treatment (pre-registered; nothing tuned)

```
corrected_proj(i, S) = proj(i, S) + beta_S[cohort] * z_mkt_vs_model(i, S)
```

* **`z_mkt_vs_model`** is D118's feature: within-position projection rank minus ECR rank, z-scored
  within (season, position), read from D118's artifact.
* **`beta_S`** is D118's walk-forward univariate slope (ridge α = 1, trained on 2021..S−1),
  refitted with D118's own `fit_ridge`. It is **checked against every one of D118's stored
  predictions to 1e-9**, and the runner raises on a mismatch.

| slope (pts per SD of disagreement) | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| established | +19.9 | +19.8 | +18.8 | +17.3 |
| rookie | +33.2 | +29.6 | +28.6 | +26.1 |

  Mean |correction| among ECR ≤ 200: ~9–11 points (established) and 16–24 (rookie); max 56–91.
* **Intercept dropped.** It would shift whole positions, which is D68's closed question. Without
  it the correction is mean-zero within each position, and D118's within-position flip statistics
  are *exactly* this treatment's.
* **No threshold.** The correction is continuous; a threshold would need a value chosen from data.
* **2021: correction ≡ 0** (no prior season in the window), so the effective sample is 2022–2025
  (k = 4). K, DST, and players without an ECR rank get 0.
* **Control:** production Alpha, with everything else identical. Insertion point:
  `load_season_static(projections_override=…)`, the one D68's X-arms use.

**The treatment could be specified without tuning, so the STOP condition did not trigger.**

---

## 3. Exact assumptions

| input | value | source | how it is used |
|---|---|---|---|
| observed flip rate, all same-position pairs (ECR ≤ 200) | **8.8%** | D118 | low-leverage p_c |
| observed flip rate, close pairs (\|proj gap\| ≤ 30) | **26.0%** | D118 | **central p_c** (picks are decided among close candidates) |
| changed-pick rate of the most aggressive existing market arm (FP_ECR_Y1) | 58.8% / 63.4% | D115 arms, this vintage | **ceiling p_c** |
| observed flip accuracy | **55.0%** | D118 | expected correct vs incorrect changes |
| observed gain per flip (raw points) | **+12.6**, season CI [−17.0, +45.3] | D118 | g; top of the CI in the GO-favourable case |
| raw → roster-value conversion | **1.0 (optimistic)** | assumption | D114 measured 0.109 for market-driven changes, D115 1.22 for the oracle's |
| SD of one-step delta on a changed pick | 55.7–82.6 (target), 56.6–71.7 (dynasty) | D115 arms X2, X3, FP_ECR_Y1, L1 | σ_c (pooled; smallest in the GO-favourable case) |
| between-season inflation over pure sampling | 1.60–2.20 (target), 0.97–1.60 (dynasty) | same arms | largest in the conservative case; 1.0 in the GO-favourable case |
| seasons | **k = 4** (2022–2025), t(.975, 3) = 3.182 | treatment definition | |
| picks | 64 per season-format; 256 treatable | D103/D115 grid | |

**Variance model check (leave-one-arm-out).** Each existing arm's observed k = 5 CI half-width is
predicted from its own changed rate and σ_c, using the *other* arms' inflation. Predictions land
at **0.71–1.43×** observed (X2 3.95 vs 4.94; X3 6.29 vs 7.53; FP_ECR 18.4 vs 15.6; L1 24.1 vs 19.7,
target). An arm's own inflation would reproduce it exactly by construction; my first draft did
that and called it "validation", and I caught and replaced it. **The power function matches a
200,000-draw Monte Carlo to within 0.001.**

**Keeping D118's four quantities apart**, as the brief asks:

| quantity | value | what it is |
|---|---|---|
| observed flip rate | 8.8% of pairs / 26% of close pairs | a *pairwise* rate, not a pick rate |
| observed flip accuracy | 55.0% | pairwise, on the whole draftable pool |
| observed gain per flip | +12.6 raw points, CI [−17, +45] | not converted to roster value |
| upper-bound regret recovery | 2.6% (target) / 3.5% (dynasty) of total regret | hindsight-selected sequencing pairs, where O is always right |
| **realistic whole-pool expectation** | **+1.1 to +3.3 points/pick** | p_c × g, still assuming a 1.0 conversion |

---

## 4. Smallest practically interesting effect (SPIE)

SPIE = D118's upper-bound regret share on the sequencing pairs × mean regret per pick:

| format | upper-bound share | mean regret/pick | **SPIE** |
|---|---|---|---|
| target (primary) | 2.61% | 137.6 | **3.58 pts/pick** (57 per draft) |
| dynasty | 3.51% | 131.9 | **4.63 pts/pick** |

**Why this is the right yardstick.** It is the most the signal was shown able to reach, on the
population chosen in its favour. It already exceeds the realistic whole-pool expectation (1–3
points). A design that cannot see the SPIE cannot see anything this signal could plausibly do.
D114's ~13 points/pick is reported as context only, never used as a threshold.

---

## 5. Expected flip rate, effect, and the MDE / power table

Expected changed picks are out of 256 treatable picks per format (2022–2025).

### `target_league` (PRIMARY)

| case | p_c | g | σ_c | infl | changed (right / wrong) | **E / pick** | SE | CI ± | **MDE 80%** | **power at SPIE (3.58)** | power at E |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **conservative** (decision basis) | 0.260 | +12.6 | 70.7 | 2.20 | 67 (37 / 30) | **+3.28** | 4.97 | 15.8 | **21.2** | **0.082** | 0.077 |
| low leverage | 0.088 | +12.6 | 70.7 | 1.90 | 23 (12 / 10) | +1.11 | 2.50 | 8.0 | 10.6 | 0.175 | 0.062 |
| GO-favourable | 0.588 | +45.3 | 55.7 | 1.00 | 150 (83 / 68) | +26.6 | 2.67 | 8.5 | 11.4 | 0.160 | 1.000 |
| *anti-conservative clustering* (16 drafts, no inflation), conservative p_c | | | | | | +3.28 | 2.25 | — | 6.8 | 0.319 | 0.276 |
| *anti-conservative clustering*, low leverage | | | | | | +1.11 | 1.31 | — | 3.9 | 0.723 | 0.125 |

Power at true effects, conservative case: **0.5 → 0.05 · 1 → 0.05 · 2 → 0.06 · 3 → 0.07 · 5 → 0.11
· 8 → 0.21 · 13 → 0.44 · 20 → 0.76**.

### `dynasty_1qb`

| case | E / pick | SE | CI ± | MDE 80% | power at SPIE (4.63) | power at E |
|---|---|---|---|---|---|---|
| conservative | +3.28 | 3.26 | 10.4 | 13.9 | 0.173 | 0.112 |
| low leverage | +1.11 | 1.50 | 4.8 | 6.4 | 0.555 | 0.084 |
| GO-favourable | +28.7 | 2.82 | 9.0 | 12.0 | 0.214 | 1.000 |
| anti-conservative, low leverage | +1.11 | 1.19 | — | 3.6 | 0.954 | 0.142 |

**Reading the only cells that look powered:**
* **GO-favourable, "power at E = 1.0".** Its expected effect of +27–29 points/pick assumes every
  changed pick gains the *top* of D118's CI (+45 raw points), with a perfect conversion, on
  59–63% of picks. That would recover ~20% of all regret, against D118's own upper bound of
  2.6–3.5%. It is not a plausible effect; it is a stress test. At the SPIE, its power is 0.16–0.21.
* **Dynasty, anti-conservative, low leverage: 0.954 at SPIE.** That scenario's own expected
  effect is 1.1 points/pick. Reaching the SPIE of 4.6 would take ~52 points per changed pick, four
  times D118's estimate. At its own expected effect its power is **0.14**.

**Across every case and both clusterings, power at the scenario's own plausible expected effect
never exceeds 0.33.**

---

## 6. Decision: **NO-GO**

| pre-registered rule | value | required | result |
|---|---|---|---|
| target, conservative case, power at SPIE | **0.082** | ≥ 0.80 | **fail** |

**The experiment was not run.** `--mode experiment` reads the power artifact and raises
`NoGoError: pre-registered power gate is NO-GO (power at SPIE 0.082 < 0.8); the frozen
experiment does not run`. It is tested both ways: it refuses on NO-GO, and on a GO it refuses to
improvise an arm that was not implemented to the specification. **No weights, thresholds or
alternative corrections were tried afterwards.** The market-vs-model line is closed for now. The
signal is real (D118) but far too small for the one-step instrument at five seasons of data.

---

## 7. Next research question (NO-GO)

> **What in the shipped decision rule loses ~27% of the per-pick regret even when it is handed
> perfect projections? Decompose the gap between `ORACLE_Y1` (the Y1 rule reading realized
> points, 72.7% recovery on this vintage) and the per-pick oracle.**

* D116–D119 closed the information side: survival and opportunity cost know what they need to
  (D116). Uncertainty carries no player-level signal (D117). Stored preseason information predicts
  ≤ 5% of projection error (D118). The one signal found is undetectable at this sample size (D119).
* The rule residual is the largest remaining piece that does not depend on unknowable
  information: ~27% of regret, **~37 points/pick**, about 3× D114's resolution. It is therefore
  measurable where D119's effect was not.
* D117 supplies a concrete first suspect: the confidence multiplier is a function of M6's
  projection. `ORACLE_Y1` changes the projections but not the `confidence` table, so under perfect
  information the risk term would still be penalising players by their *old* projection.
* D115 listed this decomposition as a lower-priority follow-up. After D116–D119 it is the
  highest-value question left.
* **A discrepancy the next phase must resolve first.** `d103_pick_regret.oracle_static`'s
  docstring says `vorp` **and `replacement_levels`** are recomputed from the realized
  projections, "leaving them stale would make the arm incoherent". The code replaces only
  `projections` and `vorp`, so the static `replacement_levels` stay at Y1's values. Under L0 the
  draft-aware levels are recomputed from `static.projections` at each pick, so the practical
  effect may be small. But it is part of the arm whose residual is being decomposed, so it must be
  measured, not assumed. It is recorded here and not changed: D119 touches no earlier phase's
  code.

---

## 8. Reproducibility, provenance and what changed

```bash
# inputs: D118's artifacts and D115's arms re-run on this vintage (see D118 §9)
uv run python scripts/research/d119_market_correction_power.py --mode power --d118 <d118 out> \
    --arms <t>/d115_arms.json --arms <d>/d115_arms.json --out <o>
uv run python scripts/research/d119_market_correction_power.py --mode experiment --out <o>   # -> NoGoError
uv run pytest tests/unit/test_d119_market_correction_power.py
```

| item | value |
|---|---|
| HEAD at run time | `a7e468be0f75b26e664a324a1f9a622c6d3bb9ec` (D118) |
| `src/alpha_squad` tree / dirty | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` / **False** |
| board vintage | `f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f` (= D116–D118; all inputs checked) |
| per season | 2021 `79599ffa…` 2022 `43f0e968…` 2023 `aa73cd3f…` 2024 `7873284c…` 2025 `0b344c7e…` |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| models | `uncertainty_catboost_v2` (M6), `rookie_features_v1` (M7) |
| input `d118_measured.json` / `d118_summary.json` sha256 | `35bffd00…` / `7e9edf90…` |
| input D115 arms (target / dynasty) sha256 | `b259beba…` / `72c5d74c…` |
| output `d119_power.json` sha256 | `d923c16c8ca72c280ef5657113c6e80a624aef1ae8733b69d10aa18eb7289026` |

**Two defects found and fixed in D119's own runner, before the decision was read:**
1. scipy's noncentral-t CDF returns NaN once the far tail underflows, which crashed the MDE solver.
   Power is now computed on |noncentrality| with the underflowed tail set to 0. It is checked
   against Monte Carlo, with a regression test.
2. The first "variance model validation" fed each arm its own inflation factor, which reproduces
   its half-width by construction. It was replaced by a leave-one-arm-out check.

**Files changed by D119 — research only:**

| file | status |
|---|---|
| `scripts/research/d119_market_correction_power.py` | **new**: power analysis and experiment gate |
| `tests/unit/test_d119_market_correction_power.py` | **new**: 24 tests |
| `docs/D119_MARKET_CORRECTION_POWER.md` | **new**: this report |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged** |
