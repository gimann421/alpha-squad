# D100 — Do M6's existing four features already separate the realized top-6, out-of-sample?

**Verdict: PROMISING BUT UNRESOLVED.** The answer is genuinely mixed and both halves matter.
M6 is beaten at top-6 identification by **one of its own input features used raw, with no model
at all** — `preseason_ecr_rank` alone finds 2.75 of 6 against M6's 1.95, on the same universe,
losing in 1 of 20 position-seasons. So information M6 already receives is being discarded (H4).
But the best rule buildable from all four features still reaches only ~2.75 of a structurally
reachable ~5.45, the advantage is concentrated at WR and RB and is **absent at QB**, and at five
season clusters the pooled effect does not survive correction for the fourteen methods compared.
**Nothing shipped. No production code, no model, no retraining, no draft run, no PR.**

---

## 1. Repository integrity (Phase 0)

| check | result |
|---|---|
| working tree at start | clean |
| branch / HEAD at start | `d99-projection-calibration`, `27cad65` (D99), stacked on D98 `be7105c` |
| `origin/main` | `277204f` (D97 merged). PR #23 (D98) **open, not merged**; PR #19 **open, not merged** |
| D99 state | complete, REJECT, no PR — unchanged by this phase |
| `models/` tree | `73b408e9bd12daecdd6a2a875e48735319b66aef` — Y1 baseline, **unchanged** |
| `league/` tree | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — Y1 baseline, **unchanged** |
| `BACKTEST_SEASONS` | `(2021, 2022, 2023, 2024, 2025)` |
| D95 empty-board contract | present (`MissingMarketBoardError`, `first_preseason_season`, `covers`) |
| D93 O-tier dispatch repair | present (`draft_forensics.py:1981`) |
| baseline tests / lint | **1350 passed, 44 deselected; ruff clean** |
| board vintage | `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99` |

Nothing differed. No merge was performed and no PR was created.

## 2. M6's actual inputs, verified against the implementation (Phase 1)

Traced through the real production path, not the documentation:
`market_snapshot` + `player_season_stats` → `models/established/season_level.py`
(`load_season_level_data` for training, `load_season_level_projection_data` for scoring — the two
carry byte-identical feature SQL, confirmed in D98) → `models/uncertainty/run.py`
(`FEATURES` imported directly from `season_level`) → `uncertainty_predictions` →
`league/replacement.py::load_season_projections` → the draft board.

| feature | definition (verified in SQL) | units | better | preseason-available? |
|---|---|---|---|---|
| `prior_ppg` | `player_season_stats.ppr_points_per_game` for season **S−1** | points/game | higher | yes |
| `prior_games` | `player_season_stats.games_played` for **S−1** | games | higher | yes |
| `prior_weighted_total` | `0.65·total(S−1) + 0.35·total(S−2)`, falling back to `total(S−1)` when S−2 is missing | PPR points | higher | yes |
| `preseason_ecr_rank` | latest **July/August** `ecr_type='ro'` FantasyPros rank scraped in year S; missing → **999** | rank | **lower** | yes |

All four are strictly pre-S. `preseason_ecr_rank` is the only one where smaller is better — every
ordering in the diagnostic declares direction explicitly and a test pins that it is the only
inverted feature, so a future feature cannot be silently ranked backwards.

**M6 models four positions only.** `models/uncertainty/run.py::POSITIONS = ("QB","RB","WR","TE")`,
confirmed against `uncertainty_predictions` (2021–2025 contain QB/RB/WR/TE rows and nothing else).
**There is no M6 model for K or DST and therefore no "M6 features" for them to contain signal** —
K and DST come from `models/baselines/kicking_defense.py` (D57), whose only inputs are the entity's
own prior one or two seasons and the walk-forward positional mean. This is reported, not
worked around; see §7.

### Redundancy — four features, about two dimensions

| | `prior_ppg` | `prior_games` | `prior_weighted_total` | `preseason_ecr_rank` |
|---|---|---|---|---|
| `prior_ppg` | 1.000 | 0.458 | **0.906** | −0.650 |
| `prior_games` | 0.458 | 1.000 | 0.642 | −0.595 |
| `prior_weighted_total` | **0.906** | 0.642 | 1.000 | −0.683 |
| `preseason_ecr_rank` | −0.650 | −0.595 | −0.683 | 1.000 |

And decisively: **corr(`prior_ppg` × `prior_games`, `prior_weighted_total`) = 0.972.** The weighted
total is very nearly a deterministic function of the other two. Three of the four features are
alternative encodings of one underlying quantity — *how much the player produced last year* — and
`preseason_ecr_rank` is the only independent dimension. D78 had already measured ECR as M6's most
valuable feature (dropping it costs **+1.83 MAE**); D100 adds that it is also the only one carrying
identification signal the others do not.

## 3. Target definition and leakage (Phase 2)

**Universe (pre-registered primary).** For each season S and position, the pool is M6's own
prediction set: the rows in `uncertainty_predictions` under the production `model_version`
(`uncertainty_catboost_v2`). This is the only pool on which *every* method being compared has a
score. Enforcing it matters: M6's training loader inner-joins season S, so it has no prediction
for a player who never played in S — leaving that unenforced would have scored M6 on a smaller
pool than its challengers and compared different denominators. Features come from production's own
`load_season_level_projection_data`, so a drift in the feature definition breaks this diagnostic
rather than silently changing what it measures.

**Target.** Realized `total_fantasy_points_ppr` for season S, left-joined and defaulted to 0.0.
Realized top-6 is the six highest within (position, season) in that pool, ties broken by
`player_id`. Season S's outcomes enter **only** as (a) the evaluation target and (b) training
labels for *other* seasons. They never touch a feature, threshold, transform, hyperparameter or
model-selection choice for S. No hyperparameter was tuned at all.

**Robustness.** The whole diagnostic was re-run on `--universe preseason` — the strictly
preseason-available set (every player with an S−1 stat line, including those who never played in
S, scored 0.0). Every conclusion below is unchanged: `U_ecr` 2.75, `U_games` 0.90, the same
paired effect (+3.20, t = 3.00). M6 is undefined on part of that pool, which is why it is the
robustness check and not the primary.

## 4. Pre-registered methodology (Phase 4/8)

Written into `scripts/research/d100_feature_signal.py`'s docstring before any result was
inspected. Methods: the four univariate features; three **fixed** rank aggregations
(`R2` all four percentile ranks, `R3` drops `prior_games`, `R4` = ppg + ECR only); three learned
diagnostics — `D_rank` Ridge(α=1) on percentile-ranked features → percentile-ranked points,
`D_clf` LogisticRegression(C=1, balanced) → binary top-6, and `D_gbm` **M6's own estimator and
hyperparameters** (CatBoost 150/3/0.08, MAE, seed 42) on raw features → raw points. Each learned
method is fitted twice: **LOSO** (train on the other four seasons — the brief's information-content
test, *not* deployable, since a 2021 fit sees 2024) and **WF** (walk-forward, train on seasons
strictly before S — deployable, undefined for 2021). `ORACLE` ranks by the realized outcome and is
6/6 by construction; it is the trivial bound and is **never** called a ceiling.

`D_gbm` is the phase's negative control: same features, same functional form, only the training
split changes. If everything retrained beats the incumbent, `D_gbm` will too, and the positive
results mean nothing. It did not — see §6.

## 5. Univariate results (Phase 3)

Pooled over 2021–2025 × QB/RB/WR/TE (20 position-seasons):

| method | top-6 overlap (of 6) | AUC | Spearman |
|---|---|---|---|
| **M6 (incumbent)** | **1.950** | 0.8990 | 0.7670 |
| `U_ecr` — ECR rank alone | **2.750** | **0.9253** | **0.7895** |
| `U_wtotal` | 2.600 | 0.8909 | 0.7344 |
| `U_ppg` | 2.400 | 0.8850 | 0.6896 |
| `U_games` | **0.900** | 0.7301 | 0.5591 |

Precision@6 and recall@6 are `overlap/6` identically here (six predicted against six realized) and
are reported in the artifacts; they add nothing to the table.

Two results stand out.

**`preseason_ecr_rank` used raw beats M6 on all three metrics** — identification, AUC and
Spearman. It is an input M6 already receives, requires no fitting, and was available every
preseason. This is not a market-versus-model comparison in the abstract; it is the same
information, used two ways.

**`prior_games` is anti-signal for identification.** 0.90 of 6 pooled and **0.00 at RB in every
season** — ranking running backs by games played never once found a top-6 RB. Its AUC of 0.73 says
it is not noise (top-6 players do play more games), but "played the most games" is not "was a
star". This closes D69's open thread: the availability/durability proxy already in the feature
set carries no top-6 identification signal, and adding it to a rank aggregation monotonically
hurts — `R2` (with games) 2.30 < `R3` (without) 2.55 < `R4` (ppg + ECR only) 2.65.

## 6. Multivariate, feature-only results (Phase 4)

| method | overlap | AUC | seasons vs M6 | paired Δ (summed over 4 positions, max 24) | 95% CI |
|---|---|---|---|---|---|
| M6 | 1.950 | 0.899 | — | — | — |
| `R4` (ppg + ECR ranks) | 2.650 | 0.913 | 4W 1T 0L | **+2.80** | [+0.41, +5.19] |
| `U_ecr` | 2.750 | 0.925 | 4W 1T 0L | **+3.20** | [+0.24, +6.16] |
| `D_rank_wf` *(deployable)* | 2.562 | 0.916 | **4W 0T 0L** of 4 | **+1.75** | [+0.95, +2.55] |
| `D_clf_wf` *(deployable)* | 2.688 | 0.915 | 3W 0T 1L of 4 | +2.25 | [−0.14, +4.64] |
| `D_gbm_wf` *(control)* | 2.250 | 0.904 | 2W 0T 2L of 4 | **+0.50** | [−2.55, +3.55] |
| `D_rank_loso` | 2.600 | 0.920 | 5W 0T 0L | +2.60 | [+0.18, +5.02] |
| `D_clf_loso` | 2.650 | 0.921 | 4W 0T 1L | +2.80 | [+0.11, +5.49] |
| `D_gbm_loso` *(control)* | 2.350 | 0.913 | 3W 0T 2L | +1.60 | [−2.75, +5.95] |
| `U_games` | 0.900 | 0.730 | 0W 0T 5L | **−4.20** | [−7.16, −1.24] |
| *ORACLE (trivial bound)* | *6.000* | *1.000* | *5/5* | *+16.20* | *[+13.81, +18.59]* |

**The negative control behaves as a null.** `D_gbm` — M6's own estimator, M6's own features, only
the split changed — lands at +0.50 (WF) and +1.60 (LOSO) with CIs spanning zero. Retraining M6's
functional form with *more* data, including the non-causal LOSO split that is allowed to see the
future, does not close the gap. The gap is therefore not a data-quantity problem and not an
artifact of "anything refitted beats the incumbent".

**Cheating on season order buys almost nothing.** LOSO ≈ WF ≈ no fitting at all: the best LOSO
diagnostic (2.65) does not beat the zero-parameter ECR rank (2.75). Whatever separation exists in
these four features is reachable without a model.

**Distributions (Phase 4A).** Realized top-6 versus the rest, mean feature value, pooled:
ECR separates by a factor of 5–16× (WR 22.7 vs 393.1; RB 32.8 vs 283.6), `prior_weighted_total` by
2.2–3.0×, `prior_ppg` by 1.7–2.6×, `prior_games` by only 1.2–1.6× — the same ordering the
identification results give.

**Mechanism.** Within (season, position), M6's output tracks `prior_weighted_total` at Spearman
0.94–0.97 and `preseason_ecr_rank` at 0.92–0.94. M6 is a smooth blend of two strongly-correlated
but differently-wrong rankings, weighted slightly toward prior production — and it identifies the
top-6 *worse than either input alone*. That is what blending does at an extreme tail: averaging
moves a player who is top-6 on one signal and middling on the other below a player who is
upper-middle on both. MAE is median regression and shrinks toward the middle by design; the top-6
is exactly where shrinking costs the most. **D78's conclusion that the observed top-of-board
compression is mostly correct behaviour stands for what it measured — point accuracy and
predictive calibration. D100 shows the same compression carries an identification cost D78 never
measured.**

**Corroboration with shipped code.** `U_ecr` is a rank and cannot enter a draft board that consumes
points. `models/baselines/market_implied.py::ecr_implied_baseline` is the already-shipped,
walk-forward, isotonic rank→points map, and by the monotone argument D99 established it must
preserve ECR's within-position order except where a flat isotonic step ties players. Measured:
summed top-6 overlap **11.00 vs M6's 7.80, Δ = +3.20, 4 wins 1 tie 0 losses, t = 2.76, 95% CI
[−0.01, +6.41]** — the same point estimate as the raw rank, with the isotonic ties costing just
enough precision to put the CI edge on zero. Those ties are severe (25–32 of 48 top-12 slots share
a predicted value), so `ecr_implied` is a signal-existence proof, **not** a ready production board:
tied projections mean degenerate VORP spacing, the failure class D91 investigated.

On MAE over that same restricted comparison, M6 (46.30) and `ecr_implied` (45.52) are not
separated — M6 is better in 1 of 5 seasons, t = −1.11. (These MAEs are not comparable to D78's
reported 40.88: the comparison is restricted to players carrying a preseason ECR rank, who are the
more prominent and higher-variance players. The restriction is required to score `ecr_implied` at
all.) So the honest framing is **not** "M6 wins accuracy and loses identification" — it is that M6
does not currently establish an advantage over the shipped ECR baseline on either criterion in this
pool.

## 7. Position-specific results (Phase 6)

Per-position, `U_ecr` minus M6 in top-6 overlap, by season:

| position | 2021 | 2022 | 2023 | 2024 | 2025 | mean Δ | record |
|---|---|---|---|---|---|---|---|
| WR | +4 | +1 | 0 | +2 | +1 | **+1.60** | 4W 1T 0L |
| RB | +1 | +1 | 0 | +1 | +1 | **+0.80** | 4W 1T 0L |
| TE | +2 | +1 | 0 | 0 | 0 | +0.60 | 2W 3T 0L |
| QB | **−1** | +2 | 0 | 0 | 0 | **+0.20** | 1W 3T 1L |

- **WR — real and consistent.** The largest gap, never negative, and the only position where the
  deployable walk-forward diagnostic is also 4/4 (`D_rank_wf` +1.00).
- **RB — real, small, consistent.** Never negative, +1 in four of five seasons.
- **TE — weak.** Entirely carried by 2021–2022; flat in 2023–2025.
- **QB — absent.** No method meaningfully beats M6; the single largest per-cell loss in the whole
  study is QB 2021. The four features contain **no exploitable additional top-6 signal at QB.**
- **K — not applicable.** M6 has no kicker model. There are no M6 features for K to interrogate,
  so D100's question is undefined at K, and D97's K identification failure is untouched by anything
  in this phase's scope. Any K work needs its own pre-registration against
  `models/baselines/kicking_defense.py`, whose year-over-year signal D57 measured at r = 0.41.

**This is the uncomfortable part of the result.** D97 flagged QB, TE and K as the problem
positions. The signal D100 found is at WR and RB, and it is *absent* exactly where D97 said the
value was.

## 8. Season-level consistency (Phase 9)

Summed top-6 overlap over the four positions, by season (max 24):

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| M6 | 5 | 8 | 9 | 10 | 7 |
| `U_ecr` | 11 | 13 | 9 | 13 | 9 |
| `D_rank_wf` | — | 10 | 11 | 12 | 8 |
| `D_gbm_wf` *(control)* | — | 6 | 9 | 12 | 9 |

`U_ecr` **never loses a season**: four wins and one tie (2023). Across all 20 position-seasons the
sign summary is **11 wins, 8 ties, 1 loss**. 2023 is a tie at every position — the one season where
M6 is not beaten anywhere — and M6's own worst season (2021, overlap 5 of 24) is where the gap is
widest (+6). That pattern is consistent with the shrinkage mechanism in §6: the blend costs most
when the two input signals disagree most.

## 9. Information ceiling (Phase 5)

Deliberately called a **feature-only diagnostic ceiling**, never an oracle — nothing below has
access to future outcomes except the trivial `ORACLE` row, which is excluded from the ceiling.

Decomposition of the 6.00-point per-position-season identification gap:

| component | overlap | share of the gap |
|---|---|---|
| found by M6 today | 1.95 | — |
| **extractable from the four features but not extracted by M6** | **+0.80** | **13%** |
| not extractable from the four features (even under LOSO) | +2.70 | 45% |
| structurally unreachable — the true top-6 player is not in M6's pool at all | +0.55 | 9% |
| = realized top-6 | 6.00 | |

The structural row is measured, not assumed: of each position's true top-6, the number present in
M6's pool averages QB 5.80, RB 5.80, WR 5.20, TE 5.00 (mean 5.45). Those absences are rookies and
players with no prior-season stat line — M5's territory, not M6's, and not addressable by any
change to these four features.

**So the honest reading is that both H3 and H4 are partly true, and H3 is the larger term.** About
13% of the identification gap is signal M6 already has and discards; about 45% is information that
is simply not in `prior_ppg`, `prior_games`, `prior_weighted_total` and `preseason_ecr_rank`, in
any combination a fair out-of-sample procedure can find.

## 10. Power and limitations (Phase 9)

- **Five season clusters.** Every interval above uses seasons as the independent unit, t(4, .975) =
  2.776 (t(3) = 3.182 for walk-forward, which cannot score 2021). Player-level n is 61–187 per
  position-season but players within a season are not independent draws, and pooling them would
  manufacture precision this design does not have.
- **Multiplicity is the binding limitation.** Fourteen methods were compared against M6. `U_ecr`'s
  t = 3.00 is a *nominal* 95% result; Bonferroni over 14 needs t(4) ≈ 5.6, and even over just the
  four pre-registered univariate arms it needs ≈ 4.6. **No single comparison here survives
  correction.** What does survive scrutiny is the pattern — 11W/8T/1L, a null negative control, and
  a mechanism that predicts the sign in advance — not any one interval.
- **Extreme-tail target with heavy class imbalance.** Six positives per cell against pools of
  61–187: base rates of 9.5% (QB), 6.1% (TE), 5.3% (RB), **3.4% (WR)**. One player moving in or out
  of a top-6 changes overlap by a whole unit, so the metric is coarse and noisy by construction.
  This also means AUC and overlap can disagree — AUC is a whole-pool quantity and is far less
  sensitive to the tail than the metric that actually matters here.
- **Season dependence.** 2021 is an outlier season for M6 (overlap 5 of 24) and contributes the
  largest single-season gap. Excluding it, `U_ecr`'s advantage drops from +3.20 to +2.50.
- **The LOSO diagnostics are not deployable** and are labelled as such everywhere. Only `U_ecr`,
  the rank aggregations, `ecr_implied` and the `_wf` arms could have been run in real time.
- **The ceiling itself is uncertain.** It rests on a small family of simple diagnostics; a
  materially better extractor of these four features may exist. The claim is that three
  independent approaches — fixed rank aggregation, linear rank regression, and M6's own gradient
  boosting under a more permissive split — all land in 2.25–2.75, which bounds the plausible range
  rather than pinning a number.

## 11. Is a downstream draft experiment justified? (Phases 10–11)

**No, and it was not run.** Phase 10's four conditions are met only partially, and one is decisive:

1. *existing features contain signal* — **yes**, +0.80 of 6.
2. *the signal is out-of-sample* — **yes**; `U_ecr` requires no fitting at all, and `D_rank_wf` is
   walk-forward.
3. *not confined to one season* — **partially**; never negative in any season, but null in 2023 and
   null at QB throughout.
4. *a concrete, minimal hypothesis for exploiting it* — **yes** (§13), **but it cannot be tested
   without building a new projection**, which is precisely what this phase forbids ("Do NOT retrain
   M6. Do NOT add features. Do NOT calibrate projections."). `U_ecr` is a rank, not points;
   `ecr_implied`'s isotonic ties would make a degenerate board. A draft run today would be a run of
   something D100 is not permitted to build.

Independently, D97 measured the between-season SD of the draft contrast at 144.5, giving an MDE of
**~180 starter points at k = 5**. A +0.80-of-6 identification change is not established to clear
that. Running the draft experiment now would repeat the mistake D93/D99 were careful to avoid.

**No 2026 sanity check either** (Phase 11). No actionable hypothesis is being carried into
production, and 2026 is not historical evidence.

## 12. Verdict

**PROMISING BUT UNRESOLVED.**

Not SHIP: the strongest effect does not survive multiplicity at five clusters, it is absent at the
position D97 cared most about (QB) and undefined at another (K), and the exploitable share of the
identification gap (13%) is smaller than the share that is simply not in the data (45%).

Not REJECT: the incumbent is beaten by its own raw input in 11 of 20 position-seasons and loses
none of the five seasons; the negative control is null; the mechanism was predicted in advance and
is visible in the correlation structure; and the repository already contains an implemented,
gate-passing arm aimed at the exact defect (§13).

**Nothing about production changes on this evidence.**

### The ten questions, answered explicitly

1. **Do the four features contain signal about eventual top-6 players?** Yes, and more than M6
   extracts — but the increment is modest (+0.80 of 6) against a much larger unextractable
   remainder (+2.70).
2. **Which features contain the most signal?** `preseason_ecr_rank`, by a distance and on every
   metric. Then `prior_weighted_total`, then `prior_ppg`. `prior_games` contains **negative**
   identification signal and dilutes any aggregation it enters.
3. **Is the signal present for QB / TE / K?** **QB: no** (+0.20, 1W/3T/1L). **TE: weak** (+0.60,
   confined to 2021–2022). **K: the question does not apply** — M6 has no kicker model.
4. **Is the signal present for RB / WR?** **Yes for both**, and this is where all of it lives:
   WR +1.60 and RB +0.80, neither ever negative in any season.
5. **Does M6 fail to exploit information already present?** **Yes.** It is beaten by its own raw
   input feature, and by a rank-target Ridge on the same four features, while M6's own estimator
   refitted under a more permissive split is not better than M6. Features and data quantity are
   held constant across that comparison; the target and loss are what change.
6. **Or is the information fundamentally absent?** **Also yes, for the larger part.** 45% of the
   gap resists every feature-only method tried, including ones allowed to see the future.
7. **Is the conclusion consistent across seasons?** Directionally yes — 0 losing seasons, 11W/8T/1L
   across position-seasons — but 2023 is null everywhere and 2021 contributes disproportionately.
8. **Is there a concrete next feature/model hypothesis?** Yes — §13.
9. **Does anything justify changing production now?** **No.**
10. **What is the smallest next experiment?** §13.

## 13. Next research question

The repository already names it. D78 pre-registered four arms; **Y2 — "drop training seasons whose
preseason board does not exist (ECR coverage below floor)" — is the fix for the ECR sentinel
defect**, the same defect D100's evidence points at: `market_snapshot` has no Jul/Aug `ro` rows
before 2020, so every training row with a target season of 2016–2019 carries
`preseason_ecr_rank = 999` regardless of who the player was (~44% of the RB training rows behind a
2026 projection), teaching M6 that a bottom-of-board consensus rank is compatible with an elite
season. Y2 was **rejected on G6** (top-of-board calibration worse at RB and WR). **Y3 = Y1 + Y2
passed all seven gates** and was deliberately not taken under the lowest-numbered-arm rule, and
D78 recorded it verbatim as "a candidate for a future phase with its own pre-registration."

**Every one of D78's seven gates is an MAE, RMSE, Spearman or top-decile-bias gate. Not one is an
identification gate** — even though `evaluation_results` already carries `top12_hit_rate` and
`top24_hit_rate` columns. G4 ("ordering is not damaged") is whole-pool Spearman, which D100 shows
is nearly blind to this question: M6 and `U_ecr` differ by 0.02 in Spearman and by 41% in top-6
overlap. D78 also measured and rejected, **on MAE alone**, a set of changes that includes the
output-transform and loss-function family D100's mechanism implicates (RMSE +2.29 MAE, Huber +0.61,
a ppg × games decomposition +0.69).

> **Smallest next experiment: re-run D78's existing Y0–Y3 arms unchanged, with a pre-registered
> top-6 identification metric added as a measured outcome alongside the seven existing gates — and
> state in advance whether identification is permitted to override an MAE gate.**

It needs no new feature, no new data source, and no new model code — `projection_specification.py`
already implements the arms and the gates. It directly tests whether the ECR-sentinel defect is the
mechanism behind D100's finding, and it forces the project to decide, before seeing the numbers,
which loss the draft product is actually optimizing. If Y3 improves identification as well as MAE,
*that* is the candidate for a real implementation phase with a downstream draft test.

Two smaller open items, recorded rather than pursued:

- **The `prior_games` question is closed.** D69's flagged availability/durability association
  carries no top-6 identification signal (0.90 of 6 pooled; 0.00 at RB in all five seasons) and
  degrades every aggregation it enters. It should not be the basis of a future arm.
- **WR is where the headroom is**, not QB. Any identification-targeted work should be measured at
  WR first, where both the effect and the class imbalance (3.4% base rate) are largest.

## 14. Reproduction

```
uv run python scripts/research/d100_feature_signal.py --out <dir>              # primary
uv run python scripts/research/d100_feature_signal.py --universe preseason --out <dir>
uv run pytest tests/unit/test_d100_feature_signal.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```

The script is read-only: it opens the database read-only, imports production's own feature loaders
and M6's own estimator definition, and writes nothing but its JSON artifacts. Its unit tests pin
that the rebuilt estimator matches `uncertainty/run.py::_new_model` exactly, that every production
feature has a declared direction, and that the pre-registered universe is enforced rather than
merely described — so the diagnostic breaks loudly rather than drifting if M6 changes.
