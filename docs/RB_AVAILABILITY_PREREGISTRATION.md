# RB availability modelling — pre-registration (EXECUTED — D70. Gates failed; nothing shipped.)

> **Status: this pre-registration has been executed.** It was implemented exactly as specified
> below (`src/alpha_squad/features/availability.py`,
> `src/alpha_squad/evaluation/rb_availability_experiment.py`), committed *before* being fitted
> against real outcomes, then run. **Gates B1 (accuracy) and B2 (targeted bias falls) both
> failed** — B2 decisively: the treatment made the RB signed bias larger, not smaller, in every
> treated season. Per the ordering below, the draft layer (B4–B9) was never run. Nothing shipped;
> production remains the **D67/W1** engine, byte-identical. Full results: `docs/DECISIONS.md` D70.
> This file is kept as the historical record of what was pre-registered and is no longer a live
> specification — a future RB-specific phase needs its own pre-registration, not a reopening of
> this one, per the "loosened after a result" prohibition its own original text stated.

Originally written as part of **D69** (`docs/DECISIONS.md`), which abandoned RB-only projection
calibration. **P1-0 remains OPEN.**

---

## 1. Why this phase, and what it is not

D67 diagnosed Alpha's residual benchmark gap as upstream of the draft engine: Alpha loses RB
starter points in all five seasons (mean **−247.7**), and M6 under-projects draftable RBs. D68
tested broad positional calibration and rejected every arm. D69 tested whether an RB-only
calibration was justified and concluded it was not, for reasons that point directly here:

- The RB residual is strongly **associated** with games played — within-season correlation
  **+0.711 / +0.797 / +0.696 / +0.724 / +0.718** across 2021–2025, i.e. roughly half of
  within-season residual variance.
- Draftable-RB mean games played moved **11.67 → 12.71 → 13.77 → 14.19 → 13.83** while mean RB
  projections stayed essentially flat (140.0 → 143.1).
- The movement is **RB-specific**: 2021→2024 change of **+2.52** games against TE +0.80, WR +0.35,
  QB −0.04, with a much flatter all-position control and no schedule change (17 games throughout).

**This phase asks a model question, not a calibration question.** A positional constant was
rejected partly because the W1 engine is near-inert to it — a uniform additive RB shift moves the
RB replacement level by the identical amount, leaving `draft_aware_vorp` unchanged (measured
ΔVORP **exactly 0.00**). Features that inform *each RB differently* do not have that problem: they
change the within-position spread, and therefore VORP.

**Explicitly not in scope:** any positional bonus, scarcity term, replacement or depth multiplier,
positional cap, round-specific rule, or change to `league/draft.py`. The draft engine is a constant.

## 2. Mechanism status — read this before designing anything

**The availability explanation is the leading hypothesis, supported by a strong and stable
association. It has NOT been established as the cause of the RB residual.** These alternatives are
live and unresolved, and the phase must be able to distinguish or at least report against them:

| alternative | why it is still open |
|---|---|
| **Winner's curse / projection-rank conditioning** | the universe is defined by projection rank, and conditioning on rank yields a positive expected residual at the top of any noisy ranking regardless of bias. D69 did not separate this. |
| **Market-varying universe** | RB n = 48/48/47/43/46 because `market_draft_demand` moves, so 2024's +44.4 is measured on a smaller, more elite set than 2021's +2.5. |
| **League-environment / usage regime change** | a season-level shift no per-player feature can capture. |
| **Model misspecification at RB** | unrelated to availability. |
| **Reverse or joint causation** | games played is realized *in-season*; it is a downstream measurement, not a preseason instrument. A model may not use it contemporaneously. |
| **Narrow survivorship** | M6's target frame is an INNER JOIN on the target season's `player_season_stats` (`models/established/season_level.py::load_season_level_data`, used by `models/uncertainty/run.py`), so a projected player who never appeared in a game log is absent from both projection and residual. |

**Design consequence, binding:** the phase may only use **preseason-knowable** inputs. Target-season
games played is the thing being predicted, never a feature.

## 3. Question and hypothesis

> **Q.** Does giving M6 preseason-knowable availability information reduce RB projection error and
> improve the W1 draft, where a positional constant cannot?

> **H1.** RB projection error is partly attributable to unmodelled availability that is
> *predictable at the player level* before the season.

> **H0 (the null this phase must be able to accept).** RB availability is either not predictable
> from preseason information, or is a league-level shift that per-player features cannot capture.
> In that case the phase reports H0 and ships nothing.

## 4. Data, population, and walk-forward boundaries

- **Residual/eval population:** unchanged from D68 — within-position projection rank
  ≤ `round(teams × market_draft_demand[pos])`, reusing
  `evaluation/projection_calibration.py::draftable_depth` and `band_edges`. Do not invent a new cut.
- **Target:** M6's existing `target_points` (season PPR total). Availability enters as a *feature*,
  not as a new target. A separate games-played model, if built, is an intermediate whose output is
  a feature.
- **Walk-forward:** unchanged from M6 — for target season `S`, train on target seasons `< S−1`,
  calibrate on `S−1`, predict `S` (`models/uncertainty/run.py`). Feature construction must obey the
  same boundary: every feature value for season `S` must be computable from data timestamped before
  `S` began.
- **Evaluable seasons:** 2021–2025 only. M6 predictions cannot be extended backwards — the `ro`
  board begins in 2020 and `preseason_ecr_rank` is one of M6's four features
  (`FIRST_RESIDUAL_SEASON = 2021`). **This limit is not negotiable and must not be relaxed to gain
  power.**
- **Treated seasons for the draft layer:** 2023–2025, **30 drafts**, carried over from D68 for
  comparability. Fixed now. Do not expand after seeing results; do not treat 2021–2022 for power.
  **Thirty drafts is a mechanism/diagnostic sample and is not sufficient on its own to establish
  that Alpha beats consensus.**

## 5. Candidate features — all preseason-knowable, all to be fixed before fitting

Committed as a closed list. No sweep, no post-hoc additions.

| # | feature | source | preseason-knowable? |
|---|---|---|---|
| F1 | multi-season games-played history (prior 2–3 seasons) | `player_season_stats.games_played` | yes |
| F2 | age at season start | existing player attributes | yes |
| F3 | position-cohort availability baseline from seasons `< S` | derived, walk-forward | yes |
| F4 | prior-season workload proxy (touches/snaps per game) | `player_week_stats` / `player_week_features` | yes |

`prior_games` is **already** an M6 feature; F1 generalizes it beyond one season. The phase must
therefore report the incremental value over the existing feature set, not the value of availability
information in the abstract.

**Forbidden as features:** target-season games played or any in-season realization; any season-level
trend term fitted using the target season; anything requiring the target season's
`player_season_stats` row.

## 6. Control and treatment

- **Control:** current M6 feature set, current projections, D67/W1 engine — i.e. forensic tier `X0`,
  already verified byte-identical to `W1` on real 2021/2023/2025 data across 9 drafts.
- **Treatment:** M6 refit with the F1–F4 additions, same walk-forward split, same hyperparameters,
  feeding the **unchanged** W1 engine through the existing single insertion point
  (`draft_forensics.py::load_season_static`'s `projections_override`).
- **Only the projection input changes.** No scoring term, no engine change.
- **Layer ordering, binding:** the projection layer (§7 gates B1–B3) is evaluated **first**. A
  treatment failing it never reaches the draft layer. This ordering is what prevents a feature set
  from being chosen by draft outcome.

## 7. Pre-registered gates

**Projection layer — evaluated first, on held-out target seasons.**

| gate | requirement |
|---|---|
| **B1 — accuracy** | pooled RB MAE and RMSE ≤ control on treated seasons, and MAE worse than control in at most one season |
| **B2 — the targeted error falls** | RB signed residual's magnitude reduced on treated seasons, and not made worse at QB/WR/TE |
| **B3 — the mechanism is real, not fitted** | the availability component must predict out-of-fold: correlation between predicted and realized player-level games played > 0 on every treated season. *If availability is not predictable, H0 is accepted here and the phase stops.* |

**Draft layer — only for treatments passing B1–B3.**

| gate | requirement |
|---|---|
| **B4 — improvement vs control** | mean realized starter points > `X0` on the 30-draft treated subset |
| **B5 — generalization** | positive in ≥2 of 3 treated seasons, and leave-one-season-out positive in all 3 folds |
| **B6 — no regression elsewhere** | QB/WR/TE/K/DST starter points not worse in aggregate; within-position Spearman not decreased |
| **B7 — roster validity** | 0 drafts with no player at a mandatory position, 0 unfilled mandatory slots, every roster exactly `roster_size`, feasibility-cap breaches not increased |
| **B8 — determinism** | two processes, `PYTHONHASHSEED` unset, byte-identical reports |
| **B9 — practical significance** | ≥ **+25** mean starter points on the treated subset — roughly 10% of the −247.7 RB deficit. Committed now so a numerically-positive-but-inert result is a failure rather than a headline. |

**Statistical significance versus consensus is reported but is explicitly NOT a gate.**

**Selection rule:** ship only if every gate passes, and then only via a separate official
`alpha-squad evaluate draft-simulation` run plus two-process determinism. If any gate fails,
nothing ships and production stays on D67/W1.

## 8. Leakage protections

1. **Structural, not procedural.** Feature construction takes the target season as an argument and
   must raise if asked for a value that would require data from that season or later — mirroring
   `projection_calibration.py::fit_arm`'s raise-on-`season >= target_season` guard, which is the
   pattern to copy rather than reinvent.
2. **Reuse the existing walk-forward split** in `models/uncertainty/run.py`; do not add a second
   splitting scheme.
3. **Pre-registration commit before fitting**, as at `30a0683` (D67) and `f467e73` (D68).
4. **The benchmark is never an estimation input.** No feature, hyperparameter or inclusion decision
   may be made from draft-layer results.
5. **A unit test per guard**, including one asserting that requesting a target-season feature value
   raises.

## 9. Abandonment conditions

Any one ends the phase with **no production change**, and that is a legitimate outcome:

1. **B3 fails** — availability is not predictable from preseason information at the player level.
   This is H0 and, on D69's evidence that the trend is league-wide rather than obviously
   player-idiosyncratic, is a genuinely likely outcome.
2. **The effect is league-level, not player-level** — a season fixed effect explains it and no
   per-player feature does. A season-level term fitted on prior seasons is a *forecast* of the
   league environment, which is a different project and must not be smuggled in here.
3. **B9 fails** — the projection improves but the draft does not move meaningfully.
4. **The improvement is confined to 2024**, the single season with the largest residual.
5. **Winner's curse is not excluded** — if the gain disappears once rank-conditioning is accounted
   for, the effect was an artifact of the universe definition.
6. **A protocol violation would be needed to make it work** — a fifth feature, a hyperparameter
   sweep, a relaxed leakage boundary, treating 2021–2022, or moving a gate after seeing a result.

## 10. Expected code and data changes, when implemented

| purpose | file |
|---|---|
| availability features | `src/alpha_squad/features/` (new module) |
| M6 feature set + walk-forward refit | `src/alpha_squad/models/uncertainty/run.py` |
| tier registration beside `X0` | `src/alpha_squad/evaluation/draft_forensics.py` |
| reuse, do not reimplement | `projection_calibration.py::draftable_depth`, `band_edges`, `load_residual_rows`; `league/replacement.py::market_draft_demand`; `draft_forensics.py::load_season_static` |
| tests | `tests/unit/` — leakage guards, feature determinism, control equivalence |
| docs | `docs/DECISIONS.md` (D70), `docs/PROJECT_STATE.md`, `docs/IMPLEMENTATION_GAP_ANALYSIS.md`, `docs/TRACEABILITY.md` |

`league/draft.py` and `league/replacement.py` are **not** touched unless every gate passes.

## 11. What is already known to be unknown

- Whether the availability movement continues; it turned down in 2025 (14.19 → 13.83), and five
  seasons cannot separate a trend from a bump.
- Whether the RB residual is bias or winner's curse.
- Whether M6's model class can express availability even given the features.
- Sample size: five residual seasons, three treatable, 30 drafts.
