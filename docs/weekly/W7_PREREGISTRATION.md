# W7 — Pre-registration: is future opportunity predictable before Friday?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any forecast was fitted and before any
opportunity-persistence statistic was computed. The audit in §2 establishes **what exists and when
it was knowable** — it deliberately does **not** measure how predictable opportunity is, because in
this phase that measurement *is* the answer, and computing it before fixing the design would let
the design follow the result.

Authority: `docs/weekly/W5_TOPBOARD_FORENSICS.md` (§17, the usage oracle), `docs/weekly/W6_UPPER_OUTCOME_RESULTS.md`
(§8, the constraint that ordering is set by features, not the objective), `CLAUDE.md`. Decision
record: `docs/DECISIONS.md` D115.

> **No change below after seeing results without a dated amendment here.**

---

## 1. The question

W5 showed that ranking by the week's **realized** usage-expected points (`ORACLE_USAGE`) recovers
53–63% of the perfect-foresight ceiling and beats ECR by +0.16 to +0.21 on positional capture@10.
W6 showed that changing what Alpha is trained to predict barely changes its ordering — the order is
set by the **inputs**. So the remaining question is about information:

> **How much of a player's week-*w* opportunity is predictable from information that demonstrably
> existed before the Friday cutoff — and does the predictable part identify the players who belong
> at the top of the board?**

Two sub-questions, both required for SUCCESS:

| | question | instrument |
|---|---|---|
| **Q1** | Is there meaningful forecastable opportunity **that Alpha does not already have**? | §6 forecast ladder |
| **Q2** | Does giving Alpha that information improve the top of the RB/WR board? | §8 ranking ladder |

**A clean "this is mostly unknowable before Friday" is a successful outcome** — it would stop the
program from chasing a ceiling that cannot be reached.

---

## 2. Audit — run first, reported as fact

### 2.1 Reproduction and parity

W5 and W6 re-run from their committed instruments before anything else (results in the results
document, §0). **Production-control parity re-confirmed directly: retraining with production's loss
reproduces all 29,376 stored weekly predictions exactly, maximum absolute difference 0.0.** No file
under `models/`, `league/`, `api/`, `cli.py`, `market/`, `features/`, `identity/`, `ingest/` or
`sources/` has changed since the weekly program began (`ec9e3c2^..HEAD`).

### 2.2 Which opportunity measures actually exist

Searched across every ingested snapshot's columns:

| measure | source | present? |
|---|---|---|
| targets | `player_week_stats`, `ep_weekly.rec_attempt` | **yes**, 100% coverage |
| carries / rushing attempts | `player_week_stats`, `ep_weekly.rush_attempt` | **yes**, 100% |
| receptions | `player_week_stats` | yes |
| target share | `player_week_stats` | **yes**, 100% |
| air-yards share | `player_week_stats` | **yes**, 100% — *not* one of Alpha's features |
| snaps / snap share | `player_week_stats.offense_snap_pct`, `snap_counts` | **yes**, 99.8–99.9% |
| team rushing attempts (→ carry share) | derivable from `player_week_stats`; `ep_weekly.rush_attempt_team` | yes |
| usage-expected fantasy points | `ep_weekly.total_fantasy_points_exp` | yes — **the quantity `ORACLE_USAGE` ranked by** |
| **routes run** | — | **ABSENT from every ingested source.** `ftn_charting` carries play-level charting (motion, play action, screens) but no per-player route participation |

**Routes are not researchable in this repository.** They are recorded as a data-acquisition item,
not approximated.

### 2.3 What Alpha already holds

Alpha's 11 `FULL_FEATURES` already contain `targets_avg_last3`, `carries_avg_last3`,
`receptions_avg_last3`, `target_share_avg_last3`, `snap_pct_avg_last3`, `fp_ppr_avg_last3`,
`fp_ppr_avg_season_to_date`, `games_played_prior` and three lagged team-environment columns. **Any
new opportunity feature must be shown to add information beyond these**, not merely re-express them
(§6.3).

### 2.4 Information-timing classes (W7's scheme)

**Note:** W7 uses the four timing classes the brief defines, which are *not* W5's classes of the
same letters. W5's "Class A" meant "Alpha already has it"; W7's means "provably pre-Friday".

| class | meaning | may enter the main test? |
|---|---|---|
| **A** | demonstrably existed before the Friday cutoff | **yes — the only class that may** |
| **B** | probably existed, but its historical timing cannot be proven | documented; one labelled sensitivity (§9) |
| **C** | only knowable after the cutoff | no |
| **D** | contains or depends on the game's outcome | no — used only as the `ORACLE_USAGE` ceiling |

| candidate predictor | class | why |
|---|---|---|
| a player's usage in **completed prior games** (targets, carries, snaps, shares, air yards) | **A** | box scores of games dated before the cutoff; plain arithmetic on completed-game facts |
| carry share (carries ÷ team carries, prior games) | **A** | arithmetic on completed games |
| usage trend and volatility across prior games | **A** | arithmetic on completed games |
| calendar weeks since last appearance | **A** | needs only the schedule and past appearances |
| **opponent identity** | **A** | the schedule is fixed months ahead |
| opponent's opportunity allowed to the position, **prior weeks of the same season** | **A** | arithmetic on completed games |
| **prior-week** depth chart (2015–2024) | **A** | a completed week's chart |
| **current-week** depth chart (2015–2024) | **B** | week-keyed, **no timestamp** — cannot show it was published before Friday |
| 2025 depth chart | **A** in principle, **unusable** | daily-timestamped, but a different schema with **no week key** |
| **lagged usage-expected points** (`ep_weekly` values for prior weeks) | **B** | *not* a plain box-score quantity: it is the output of a **fitted model**, and the historical values were produced by a model that may have been trained on seasons after the one it is scoring. Probably informative, not provably point-in-time |
| injury / practice status, **STRICT** (`date_modified` < cutoff date) | **A** | but W5 measured **0.2%** coverage — the file is one final row per player-week, 75.5% last edited on Friday |
| injury / practice status, same-day **FRIDAY** | **B** | edited on the cutoff date, possibly after it |
| teammate availability | **A** (STRICT, 0.2%) / **B** (FRIDAY) | same file |
| Vegas spread, total, implied team total, line movement | **not ingested** | absent from every source — cannot be tested, only recorded |
| routes run | **not ingested** | §2.2 |
| coaching / personnel / role announcements | **not ingested** | no structured source |
| **the week's own realized usage** | **D** | it is the outcome's cause |

**Injury status is not included in the main test** for a measured reason, not an assumed one: its
only provably-pre-Friday form covers 0.2% of player-weeks (W5 §9), so any effect it had would be
unmeasurable, and W5 found the permissive form explains no more top-of-board regret than its
population share.

---

## 3. Opportunity targets — fixed now

All realized in week *w*, for players who played (the same "given that he plays" universe every
prior phase used; availability stays a separate concept, as W1 required).

| id | target | positions | role |
|---|---|---|---|
| **T_XFP** | `total_fantasy_points_exp` — usage-expected fantasy points | RB, WR, TE | **PRIMARY** — the exact quantity `ORACLE_USAGE` ranked by |
| T_OPP | targets + carries | RB, WR, TE | secondary |
| T_TGT | targets | RB, WR, TE | secondary |
| T_CAR | carries | RB | secondary |
| T_TSH | target share | WR, TE | secondary |
| T_SNP | snap share | RB, WR, TE | secondary |

`T_XFP` is primary because it is the only opportunity target whose ceiling has already been priced
in ranking terms. The Half-PPR version subtracts half an expected reception (`0.5 ×
receptions_exp`), exactly as W5's Half-PPR oracle did.

---

## 4. Predictor sets — fixed now

Every feature is computed from **strictly prior appearances** with the same convention Alpha's own
panel uses (`ROWS … PRECEDING AND 1 PRECEDING` over a player's appearances), and verified by the
redaction gate in §11.

**S0 — Alpha's own information.** Exactly the 11 `FULL_FEATURES`, missing values filled with 0.0
exactly as production does.

**NEW — Class A, not in Alpha (9 features):**

| feature | definition |
|---|---|
| `opp_last1` | targets + carries in the most recent prior appearance |
| `snap_pct_last1` | snap share in the most recent prior appearance |
| `opp_trend` | `opp_last1` − mean(targets + carries) over prior appearances 2–4 |
| `opp_sd_last3` | standard deviation of targets + carries over the last 3 appearances |
| `air_yards_share_avg_last3` | mean air-yards share, last 3 appearances |
| `carry_share_avg_last3` | mean of carries ÷ team carries, last 3 appearances |
| `weeks_since_last_game` | calendar weeks since the last appearance this season (missing if none) |
| `opponent_opp_allowed_prior` | this week's opponent's mean targets + carries allowed per player-game to the position, over prior weeks of the same season, reported only with ≥ 3 weeks |
| `depth_team_prior` | the player's `depth_team` (1/2/3) on the **previous** week's chart; missing for 2025 (schema break) |

**REDUNDANT — a control, not a candidate (4 features):** `targets_avg_last5`, `carries_avg_last5`,
`snap_pct_avg_last5`, `target_share_avg_last5`. These re-express information Alpha already has over a
longer window. They exist to measure how much apparent gain comes from **adding more of the same**,
which is the double-counting hazard §6.3 guards against.

**CLASS_B — exploratory only (1 feature):** `xfp_avg_last3`, the mean of lagged usage-expected
points. §2.4 explains why it is Class B. It may not enter the verdict.

**Missing values in NEW / REDUNDANT / CLASS_B** are median-imputed from the training fold with a
missing-indicator column for the linear models, and left as missing for CatBoost, which handles them
natively. Zero-filling them would invent information — a missing `depth_team_prior` is not "depth
0" and a missing opponent measure is not "allowed zero".

---

## 5. Walk-forward, universe, statistics

**Walk-forward exactly as Alpha trains**: for target season *S*, every model is fitted on
`[2015, S − 1]` and predicts season *S*. Refit once per season. No model sees any week of the season
it predicts.

**Evaluation universe**: identical to W3–W6 — 79 weeks, 2021–2025, the ECR positional board
restricted to players who played and whom Alpha covers. `T_XFP` is additionally restricted to
player-weeks with a realized usage row; coverage is reported per position.

**Unit of replication is the week (n = 79).** Paired within week; 95% bootstrap CI over weeks
(10,000 resamples, seeds 0–9); Wilcoxon and win/loss counts. Measured MDE on positional capture@10
(W5): RB 0.0206, WR 0.0196, TE 0.0193.

---

## 6. Q1 — the forecast ladder

### 6.1 Simple baselines first (no fitting)

For each target, from the target's own prior values:

| id | forecast |
|---|---|
| **BL_LAST** | the value in the most recent prior appearance |
| **BL_MEAN3** | mean of the last 3 appearances |
| **BL_WMEAN3** | weighted mean of the last 3 appearances, weights 0.5 / 0.3 / 0.2, renormalised when fewer exist |
| **BL_TREND** | `BL_MEAN3 + 0.5 × (last value − mean of appearances 2–3)` |
| **BL_COMBO** | ridge on {`BL_LAST`, `BL_MEAN3`, `BL_WMEAN3`, `BL_TREND`} + {`snap_pct_last1`, `weeks_since_last_game`, `games_played_prior`} |

### 6.2 Forecast models (all ridge, `alpha = 1.0` on standardised features, **no tuning**)

| id | features | answers |
|---|---|---|
| **M_S0** | S0 | what Alpha's own information says about opportunity |
| **M_NEW** | S0 + NEW | **the primary forecast** — Alpha's information plus every Class A signal it lacks |
| **M_RED** | S0 + REDUNDANT | the double-counting control |
| **M_CB** | S0 + NEW, `CatBoostRegressor(iterations=200, depth=4, learning_rate=0.05, random_seed=42, loss_function="RMSE")` | *is the ceiling limited by the linear form, or by the information?* |
| **M_B** | S0 + NEW + CLASS_B | **exploratory** — what a Class B source would add |

**Ridge is primary** because the purpose is measurement and a linear model's ceiling is
interpretable. CatBoost uses production's hyperparameters unchanged — it is a model-form check, not
a search. RMSE is its loss because the target is *expected* opportunity, a conditional mean, and W6
already showed the loss barely moves an ordering. Nothing else is tried.

### 6.3 Metrics

Per (target, forecast, position): per-week Pearson and Spearman within the positional universe,
pooled R², MAE, top-10 and top-20 capture **of the realized target**, and calibration by predicted
decile. Reported per season and by predicted fantasy-rank band (top 5 / 10 / 20 / 50 / deeper) so
it is visible whether forecastability is concentrated where the ranking problem is.

**The double-counting test.** `Δ_NEW = M_NEW − M_S0` and `Δ_RED = M_RED − M_S0` on per-week Spearman
of `T_XFP`. New information exists only if `Δ_NEW` is real **and** exceeds `Δ_RED`.

---

## 7. Criterion C1 — "meaningful NEW forecastable opportunity exists"

At a position, **all of**:

1. `Δ_NEW` on per-week Spearman of `T_XFP` has a 95% CI excluding zero;
2. mean `Δ_NEW` ≥ **+0.02** — the practical floor W4 established and W6's amendment A1 showed is
   necessary on both sides of a rule, because two highly-correlated forecasts make trivial
   differences "significant";
3. `Δ_NEW − Δ_RED` has a CI excluding zero — the gain is not just re-expression.

---

## 8. Q2 — the ranking ladder

| level | board | information |
|---|---|---|
| **L0** | `CF_A` | current Alpha — production's stored predictions |
| **L1** | `ALPHA_PLUS_OPP` | Alpha's model retrained with S0 + NEW: **production's CatBoost, production's hyperparameters, production's MAE loss, the same walk-forward** — one change, the added Class A features |
| **L2** | `ORACLE_USAGE` | perfect knowledge of the week's usage (W5) — Class D ceiling |
| **L3** | `ORACLE_OUTCOME` | perfect foresight (W5) |
| — | `FORECAST_USAGE` | rank by `M_NEW`'s forecast of `T_XFP` — the realistic analogue of `ORACLE_USAGE` |

**Two descriptive ratios on positional capture@10** (not gates; descriptive decompositions, not
proof of cause):

    ladder share        R_L1 = (L1 − L0) / (L2 − L0)
    forecast share      R_F  = (FORECAST_USAGE − L0) / (ORACLE_USAGE − L0)

`R_F` can be **negative** — ranking by forecasted usage alone discards everything else Alpha knows —
and a negative value is reported, not rescaled.

`ALPHA_PLUS_OPP` must reduce to production exactly when NEW is empty; that is its fidelity gate.

### 8.1 Criterion C2 — "it improves the top of the board"

`ALPHA_PLUS_OPP − CF_A` on positional capture@10 at RB **or** WR: ≥ **+0.02** with a 95% CI excluding
zero, **and** W6's three genuineness checks (≥ 60% of decided weeks won; precision@10 moves the same
way; the W5 copula-null cliff shrinks), **and** no practical guardrail breach.

**Guardrail breach** (with W6's amendment A1 applied): a degradation whose CI excludes zero **and**
whose magnitude is ≥ **0.005**, in any of: TE capture@10 · any position's capture@50 · FLEX capture@25
· any position's Spearman.

---

## 9. Verdict — evaluated in this order, so exactly one applies

W6's pre-registration let two verdicts fire at once. These are evaluated top to bottom and the
first that holds is the verdict.

| order | verdict | criterion |
|---|---|---|
| 1 | **HARM** | `ALPHA_PLUS_OPP` capture@10 at RB or WR has a CI excluding zero in the negative direction, **or** a practical guardrail breach with no C2-qualifying gain |
| 2 | **SUCCESS** | C1 **and** C2 at the same position (RB or WR) |
| 3 | **PARTIAL** | C1 at RB or WR, **and** a positive `ALPHA_PLUS_OPP` capture@10 effect with a CI excluding zero that falls short of C2 (sub-threshold, a failed genuineness check, or a breach) |
| 4 | **NO EFFECT** | anything else — opportunity mostly not forecastable beyond Alpha, **or** forecastable but not moving the top of the board |

The Class B sensitivity (`M_B`) and every other exploratory analysis are **excluded** from this
table.

---

## 10. Robustness — fixed now

1. **Leave-one-season-out** on `Δ_NEW` and on `ALPHA_PLUS_OPP − CF_A` capture@10.
2. **Per-season** reporting of both.
3. **Weekly distribution** of both, not only the mean.
4. **By predicted fantasy-rank band** — does forecastable opportunity help the top more than the
   rest?
5. **Half-PPR replication** of the ranking ladder. Half-PPR never selects anything.

No further slicing.

---

## 11. Leakage and validity gates — all must pass before any result is read

| gate | check |
|---|---|
| **G1** | production parity: `ALPHA_PLUS_OPP` with no added features reproduces the stored predictions exactly |
| **G2** | **no future usage** — every NEW, REDUNDANT and baseline feature for (player, *S*, *w*) is **unchanged** when that week's and every later week's `player_week_stats` rows are physically deleted |
| **G3** | no post-Friday injury — the main feature list reads no injury field |
| **G4** | no post-Friday depth chart — `depth_team_prior` is unchanged when the current week's chart is deleted |
| **G5** | no Vegas / no market — no feature reads a market or ECR source |
| **G6** | no realized game information in context — `opponent_opp_allowed_prior` unchanged under G2's redaction |
| **G7** | walk-forward — no training frame contains the season it predicts |
| **G8** | Friday cutoff — zero evaluated players whose team had already kicked off |
| **G9** | identical universe across every board and forecast |
| **G10** | determinism — the runner is byte-identical on a repeat run |
| **G11** | upstream — W3, W4, W5, W6 still reproduce exactly |

**If any gate fails: stop, fix, re-run the affected analysis, document it — and only then read
results.** W5's G10 and W6's rule defect are the precedents.

---

## 12. A priori predictions, recorded before any result

Recorded so they can be wrong in public. In W5 three of eight were wrong; in W6 four of eight.

1. **Opportunity is materially more predictable than fantasy points**: per-week Spearman of the
   `T_XFP` forecast will land around 0.70–0.80, against Alpha's ~0.58–0.67 for points.
2. **But Alpha's own information already captures most of it**: `Δ_NEW` will be below the +0.02
   floor at every position, so **C1 will fail**.
3. **`Δ_RED` will be about as large as `Δ_NEW`** — most of the "new" features' contribution is
   re-expression of what Alpha holds.
4. **Ridge ≈ CatBoost** — the limit is information, not model form (W6's lesson, one level up).
5. **`FORECAST_USAGE` will rank worse than current Alpha** — `R_F` negative — because ranking on
   usage alone discards efficiency, and `ORACLE_USAGE`'s advantage lives in week-specific usage
   surprises no forecast can see.
6. **`ALPHA_PLUS_OPP` will be null on capture@10** — below the MDE at RB and WR.
7. **The ladder share `R_L1` will be under 10%**: most of the usage oracle's value is unknowable on
   Friday.
8. **TE opportunity will be the least forecastable** of the three positions.
9. **The Class B sensitivity will add a small but measurable amount** beyond NEW.
10. **Expected verdict: NO EFFECT.**

If the results contradict these, the results win and the contradiction is reported prominently.

---

## 13. What W7 may NOT do

Modify production or any file under `models/`, `league/`, `api/`, `cli.py`, `market/`, `features/`,
`identity/`, `ingest/`, `sources/`; add ECR or any expert ranking; add any feature beyond §4's fixed
lists; tune the ridge penalty, CatBoost or any threshold; select a model or feature set after seeing
results; search feature combinations; let a Class B/C/D quantity enter the main test; or present an
exploratory result as the verdict.

---

## 14. Amendments

*(None yet.)*
