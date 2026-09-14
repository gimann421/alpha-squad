# D99 — Can projection calibration improve top-6 identification?

**Verdict: REJECT** for the question asked. Per-position calibration of the pre-registered forms
**cannot** improve within-position top-6 identification — not empirically, but *by construction* —
and the one channel it can move was already rejected on other grounds in D68. Nothing shipped, no
production code touched.

---

## 1. Repository / baseline status

| check | result |
|---|---|
| working tree | clean |
| branch / HEAD | `d99-projection-calibration`, stacked on D98 (`be7105c`) |
| `origin/main` | `277204f` (D97 merged; PR #23/D98 open, **not** merged) |
| `models/` | `73b408e9bd12daecdd6a2a875e48735319b66aef` — Y1 baseline |
| `league/` | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — Y1 baseline |
| `BACKTEST_SEASONS` | `(2021, 2022, 2023, 2024, 2025)` |
| D93 O-tier dispatch repair | present |
| D95 empty-board contract | present (`MissingMarketBoardError`, `first_preseason_season`) |
| tests / lint | 1350 passed, 44 deselected; ruff clean |

*(The brief's quoted `league/` hash carries a transcription typo — a 41st trailing `9`. The real
40-character hash matches exactly; this is not a repository discrepancy.)*

## 2. The existing M6 / calibration path

`market_snapshot` → `models/established/season_level.py` (`FEATURES`, incl. `preseason_ecr_rank`,
validated in D98) → M6 (`models/uncertainty/run.py`) → `uncertainty_predictions` →
`league/replacement.py::load_season_projections` → the draft board.

**The central Phase-1 finding: the experiment D99 asks for already exists and has already run.**
`evaluation/projection_calibration.py` was committed in **D68** *before* any arm was fitted, and
pre-registers exactly the forms this brief proposes:

| arm | form | maps to D99's Phase 3 |
|---|---|---|
| `X0` | `p' = p` (control) | — |
| `X1` | `p' = p + b_pos` | **A**, per-position intercept |
| `X2` | `p' = a_pos + b_pos·p` | **B**, per-position linear |
| `X3` | `p' = p + b_{pos,band}` | rank/percentile-aware |
| `X4` | `p' = p + λ_pos·b_pos` (empirical Bayes) | **C**, reliability/shrinkage |

D68's recorded outcome: **every arm improved raw MAE (63.29 → 61.83–62.88) and every arm failed
its pre-registered gates (G3 or G4), every G3 failure at TE or WR. Nothing shipped.** D69
separately assessed an RB-only arm and abandoned it before implementation.

**K and DST are excluded from every arm by that pre-registration** (D57: year-over-year K r=0.41,
DST r=0.29 — a bias correction on a signal that weak fits noise; they also carry no `confidence`).
So D99's request to calibrate **K cannot be answered with the existing infrastructure**, and any K
arm would require its own pre-registration. That is reported, not worked around.

## 3. Data and leakage semantics

`fit_arm` **raises** if handed any training row from the target season or later — a structural
guard, not a convention. Fitting on a residual from season *T* is legitimate only because M6's own
split already made *T*'s prediction out-of-sample (train on target seasons < S−1, calibrate on
S−1, predict S).

The eligibility prior (`MIN_TRAINING_SEASONS = 2`, `MIN_TRAINING_ROWS = 30`) has a hard
consequence, declared in D68 before measurement:

| target season | training seasons available | status |
|---|---|---|
| 2021 | 0 | **control by construction** |
| 2022 | 1 | **control by construction** |
| 2023 | 2 | treated |
| 2024 | 3 | treated |
| 2025 | 4 | treated |

**Only 3 of 5 season clusters are treatable at all.** This is the binding constraint on the whole
phase and is quantified in §9. Walk-forward is used rather than leave-one-season-out: LOSO would
let a 2023 fit see 2024 and 2025, which is exactly the leakage `fit_arm` refuses.

## 4. Pre-registered metrics and hypotheses

Recorded in `scripts`-side docstring **before results were inspected**:

- **PRIMARY** — per-position top-6 identification: overlap, precision@6, recall@6.
- **SECONDARY** — Spearman; MAE. Neither is a success criterion: D68 already showed every arm
  improves MAE while failing its gates, so MAE moving is known *not* to be evidence.
- **DOWNSTREAM** — oracle-gap capture, run **only** if an arm first clears identification.

**H0, stated in advance:** `X1`, `X2` and `X4` apply a per-position map that is **monotone
increasing** in the projection (`X1`/`X4` add a constant; `X2` is affine with `b_pos > 0`). A
monotone increasing map cannot change the *order* of players within a position, and top-6-by-
position is a pure function of that order. Therefore per-position top-6 must be **exactly**
unchanged for those arms. `X3` adds a band-dependent constant and can reorder, but only across a
band edge.

## 5–6. Primary result — identification is invariant

Treated seasons (2023–2025), walk-forward, leakage guard active:

**Per-position top-6 overlap (of 6)**

| pos | X0 | X1 | X2 | X3 | X4 |
|---|---|---|---|---|---|
| QB | 2.00 | 2.00 | 2.00 | **2.33** | 2.00 |
| RB | 1.67 | 1.67 | 1.67 | 1.67 | 1.67 |
| WR | 1.67 | 1.67 | 1.67 | 1.67 | 1.67 |
| TE | 2.67 | 2.67 | 2.67 | 2.67 | 2.67 |
| K | 1.33 | 1.33 | 1.33 | 1.33 | 1.33 |
| DST | 2.33 | 2.33 | 2.33 | 2.33 | 2.33 |

**H0 check — cells where top-6 overlap differs from control, out of 30 (season × position):**

| arm | differing cells |
|---|---|
| X1 | **0 / 30** |
| X2 | **0 / 30** |
| X4 | **0 / 30** |
| X3 | **1 / 30** — (2024, QB): 2 → 3 |

H0 holds exactly. Precision@6 and recall@6 are identical to overlap/6 here (6 predicted vs 6
realized) and therefore equally invariant. Spearman is unmoved (QB 0.738 → 0.735–0.740). MAE moves
slightly and **X2 materially damages TE (27.17 → 42.17)** — consistent with D68's finding that
every G3 failure was at TE or WR.

The single X3 improvement is 1 cell in 1 of 3 treated seasons. That is not directional consistency
across seasons; it is one player crossing one band edge.

**This is the answer to the phase's primary question, and it is structural rather than
statistical.** D97's identification failure (top-6 overlap 23–40%) is a failure to *rank players
within a position*. Per-position calibration rescales a position; it never reorders it. No amount
of data would change this.

## 7. What calibration *can* move — cross-position allocation

Within a position the order is invariant; **across** positions it is not, and that is the channel
D97 actually cared about (production takes its first QB in round 2.1; the oracle waits to 7.1).
Diagnostic on treated seasons:

| arm | top-24 members changed | first QB, overall rank | QBs in top 24 |
|---|---|---|---|
| X0 (control) | — | **5.0** | 3.33 |
| X1 | 0.67 / 24 | 5.0 | 3.33 |
| X4 | **0.00 / 24** | 5.0 | 3.33 |
| X2 | 1.67 / 24 | **10.3** | 3.00 |
| X3 | 2.33 / 24 | **11.0** | 2.33 |
| *ORACLE (realized board)* | — | *10.0* | — |

Two things follow:

1. **X1 and X4 are inert on the draft board by construction.** A uniform additive shift at a
   position moves that position's replacement level by the same constant, so `draft_aware_vorp` is
   unchanged. D69 recorded exactly this property; it is confirmed here (X4 changes 0 of 24).
2. **X2 and X3 do move allocation, and in D97's predicted direction** — first-QB rank 5.0 → 10.3 /
   11.0, against an oracle of 10.0.

That is a real signal, and it is honestly reported. But it is **not the primary metric**, the arms
producing it were already rejected by D68's pre-registered gates, and X2 buys it while damaging TE.
Inventing a new gate now to promote it is precisely the protocol violation this phase forbids.

## 8. Downstream draft test — deliberately NOT run

Phase 7 is conditional on an arm clearing identification. None did (0/30, 0/30, 0/30, 1/30). Per
the pre-registered stopping rule the downstream test does not run, and no 2026 sanity check (Phase
8) is warranted either.

## 9. Power — why the open thread cannot be resolved now

Only **3** season clusters are treatable. Using the between-season SD measured on this exact
instrument in D97:

| contrast | SD | k = 5 | k = 3 |
|---|---|---|---|
| PROD − NAIVE (target) | 144.5 | MDE **179.4** | MDE **359.0** |
| ORACLE − PROD (target) | 138.4 | MDE 171.8 | MDE **343.8** |

A 3-cluster draft experiment has an MDE of **~345–360 points — larger than Y1's entire decision
apparatus (+213.8)**, and 14× the 25-point economic threshold. The cross-position signal in §7
cannot be distinguished from noise by any experiment this instrument can currently run. Running one
would repeat precisely the mistake the brief warns against.

## 10. Reproduction

```
# identification (primary) + H0 check
uv run python scripts/../<scratchpad>/d99_identification.py
# artifacts: d99_ident.json  (per season × arm × position rows)
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```

All measurement used the shipped, already-pre-registered D68 machinery
(`evaluation/projection_calibration.py::calibrated_season_projections`), whose `fit_arm` refuses
leaked training rows structurally. No production path was modified.

## 11. Verdict

**REJECT.** Per-position calibration cannot improve top-6 identification, for a reason that is
mathematical rather than empirical: identification depends on within-position *order*, and these
calibrations are monotone within a position. D97's recommendation (#1, "per-position M6
calibration") is therefore **closed as specified** — it targets the wrong mechanism for the
problem D97 itself identified.

## 12. Next research question

The identification failure is a **ranking** problem, so any fix must change within-position
ordering — which means new *information*, not a rescaling of existing predictions. The smallest
defensible next question:

> **Does M6 have access to any feature that separates the realized top-6 from the projected top-6
> within a position — and is that separation present out-of-sample?**

Concretely: M6 has four features (`prior_ppg`, `prior_games`, `prior_weighted_total`,
`preseason_ecr_rank`). D97 measured that projected-top-6 capture is ~0% at QB/TE/K while the
realized top-6 holds +69.7 VORP at QB. Before adding anything, measure whether the *existing*
features already contain separating signal M6 is discarding (e.g. `prior_games` as an
availability/durability proxy, which D69 flagged as the leading unexplained association).

That is a diagnostic on the existing feature set — cheap, no retraining, no new data source — and
it distinguishes "M6 is under-using what it has" from "the information is not in the data", which
determines whether a projection change is worth attempting at all.
