# W5 — Why does Alpha's within-position ranking fail at the top?

**Status: COMPLETE.** Run exactly as pre-registered in `docs/weekly/W5_PREREGISTRATION.md`,
which was committed **before** the instruments and before any result existed (commit `37a7428`).
**No model was built, fitted, tuned or retrained. No feature was added. No ECR was used anywhere.
No production file changed.**

Provenance: Alpha `ml_catboost` (`WEEKLY_PROJECTION_BASE_MODEL`) as written by the unmodified
`alpha-squad train established`; ECR vintage `e270d790…5db9a5`, identical to W1/W2/W3/W4; 79
weeks (2021–2025), Full PPR **and** Half-PPR, Friday cutoff; 22,413 evaluated player-weeks.
Instruments: `scripts/research/w5_topboard_forensics.py`, `w5_validity_gates.py`,
`w5_miss_predictability.py`. Results: `reports/weekly/w5_results.json`, `w5_e1.json`.

---

## 1. Executive summary

**The statistic that motivated this phase does not mean what it was taken to mean, and there is
still a real problem underneath it.**

W4 reported that `corr(predicted, realized)` among Alpha's top-of-board players falls to RB
**0.251** / WR **0.222** / TE **0.141**. W5 built the missing comparison — a ranker with Alpha's
**own overall Spearman** and **no top-specific structure at all** — and that ranker scores
**0.151 / 0.110 / 0.142** on the same statistic. **Range restriction accounts for the entire
drop.** Conditioning on a high predicted value truncates the predictor's variance; any ranker
shows it. Alpha actually retains **1.7× to 2.3×** more top-of-board ordering signal than a
uniform-quality ranker does.

**But on the metric the product is graded on, a genuine cliff exists at RB and WR.** Against the
same null, on positional points-captured@10:

| | actual − null | 95% CI | weeks | verdict |
|---|---:|---|---:|---|
| **RB** | **−0.0710** | [−0.0916, −0.0505] | 21–58 | **CLIFF** |
| **WR** | **−0.0800** | [−0.0999, −0.0607] | 15–64 | **CLIFF** |
| **TE** | −0.0096 | [−0.0289, +0.0096] | 38–41 | **NO CLIFF** |

Negative in all five leave-one-season-out folds at RB and WR, replicated in Half-PPR
(−0.0794, −0.0873), and sharply depth-localised: at RB the gap runs −0.099 at depth 5, −0.071 at
10, −0.022 at 20, and turns **positive** (+0.006) at depth 50. Alpha is *better* than the null
deep in the board and worse at the top. **TE has no cliff at any depth beyond 5.**

**The mechanism is systematic selection, not signal collapse, and the information it needs is
already in the model.** The cohorts carrying disproportionate missed regret are the ones Alpha's
two dominant features reward — `HIGH_SNAP` (WR +80%, TE +41% relative lift), `HOT_L3` (WR +86%,
RB +42%), `ELITE_PRIOR_SEASON` (WR +133%, RB +70%, TE +52%) — and the genuine top-10 finishers it
misses sit at **median predicted rank 20–29**, not deep in the board. Alpha finds the right
*group* and cannot order inside it.

**No pre-cutoff information class clears the materiality bar.** Injury designation (§9),
depth chart (§10), opponent (§12), role change (§8) and team environment (§11) each fail at least
one of the three pre-registered criteria, most of them badly. And the misses are **not
predictable** from pre-cutoff information at the two positions that have a cliff: AUC **0.4875**
(RB) and **0.4957** (WR), both below their own permutation 95th percentile.

**The one large, reachable prize is opportunity.** Ranking by the week's realized usage —
perfect opportunity foresight, **zero** conversion foresight — recovers **53–63%** of the
perfect-foresight ceiling on capture@10 and beats ECR by **+0.159 to +0.206**, four to eight
times the entire Alpha-vs-ECR gap.

**W5 decision:** do **not** open an information-acquisition phase. Two candidates survive, both
about how the target is represented rather than what the model is fed. §25 designs the cheaper
one as a falsifiable W6.

---

## 2. W3 / W4 reproduction

Re-run from the committed instruments before anything new was interpreted.

| | leaves compared | max abs difference | structural differences |
|---|---:|---:|---:|
| **W3** (`w3_alpha_benchmark.py`) | 46,756 numeric of 49,003 | **0** | 0 |
| **W4** (`w4_flex_forensics.py`) | 126,844 numeric of 129,113 | **0** | 0 |

Not "to six decimals" — exactly zero, with no key present in one run and absent in the other. The
universe, weeks, cutoff, ground truth and metric definitions are unchanged from W2 onward.

W5's own positional control reproduces W3's positional numbers exactly as well: RB Spearman
0.6679, WR 0.6360, TE 0.5763, and the Alpha−ECR gaps −0.0375 / −0.0305 / −0.0343.

---

## 3. Where the top-of-board cliff occurs

### 3.1 The instrument

"Correlation among the predicted top-K" is computed on a subgroup **selected by the predictor**.
It is attenuated by range restriction whether or not the model has any top-specific defect, so
comparing it to the full-board correlation cannot establish a cliff. W5 therefore builds a
**calibrated copula null**: for each (week, position) cell, a synthetic ranker drawn to have
*exactly* that cell's own Spearman — against that cell's own tie structure — and no top-specific
structure whatsoever. 200 draws per cell, deterministic seeds.

The null's achieved Spearman matches its target to **7.7 × 10⁻⁶** across sampled real cells
(gate G9), and the cliff test's `spearman` row is `−0.0000` at every position, which is the
instrument checking itself: the two rankers are identical on the statistic they were matched on,
and differ only in *where* their errors fall.

### 3.2 The curve

Actual minus null, paired within week (`*` = 95% CI excludes zero):

| | ρ | c@5 | c@10 | c@20 | c@25 | c@50 | p@5 | p@10 | p@20 | p@50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **RB** | −0.0000 | **−0.0986\*** | **−0.0710\*** | **−0.0223\*** | −0.0084 | **+0.0062\*** | **−0.1366\*** | **−0.1083\*** | **−0.0199\*** | **+0.0109\*** |
| **WR** | −0.0000 | **−0.1137\*** | **−0.0800\*** | **−0.0397\*** | **−0.0315\*** | +0.0015 | **−0.1432\*** | **−0.1062\*** | **−0.0601\*** | +0.0037 |
| **TE** | −0.0000 | **−0.0292\*** | −0.0096 | **+0.0249\*** | **+0.0245\*** | −0.0020 | −0.0219 | −0.0159 | **+0.0319\*** | **+0.0106\*** |
| **QB** | +0.0000 | −0.0169 | **−0.0151\*** | **+0.0127\*** | **+0.0115\*** | — | −0.0167 | **−0.0286\*** | +0.0039 | — |

**The cliff is sharply localised to the top 20 and reverses below it.** Alpha spends ordering
accuracy at the top and recovers it deeper — at depth 50 it is *significantly better* than a
ranker of its own overall quality.

By the pre-registered rule (§5: CI excludes zero, negative, |d| ≥ 0.02 on capture@10):
**RB CLIFF · WR CLIFF · TE NO CLIFF.** QB's effect is significant but −0.0151 < 0.02, so NO CLIFF
by the rule; QB is excluded from decision rules in any case.

### 3.3 Band-by-band ordering accuracy

Alpha's own pairwise accuracy, by predicted-rank band:

| | 1–10 | 11–25 | 26–50 | 51–200 |
|---|---:|---:|---:|---:|
| RB | **0.5621** | 0.5625 | 0.6029 | 0.6036 |
| WR | **0.5496** | 0.5388 | 0.5602 | 0.6689 |
| TE | 0.5821 | 0.5877 | 0.5686 | 0.5873 |

At RB and WR the top band is the **worst-ordered band on the board**, and the deepest band the
best. TE is flat — the same split the cliff test finds.

---

## 4. RB forensics

Cliff **−0.0710** on capture@10 (CI [−0.0916, −0.0505]), stable across all five LOSO folds
(−0.0668 to −0.0787, all significant) and in Half-PPR (−0.0794).

* **26.5%** of the slots Alpha puts in its RB top-10 are filled by a player who finishes outside
  the realized top-24.
* The top-10 finishers it misses sit at **median predicted rank 22**; **44.6%** were already in
  Alpha's 11–20 and **89.8%** inside its top 40. Only 10.2% come from beyond rank 40.
* Excess missed regret concentrates in `ELITE_PRIOR_SEASON` (+70%), `HOT_L3` (+42%),
  `VOLATILE_ROLE` (+22%) and `OPPORTUNITY_UP` (+36%) — and `HIGH_SNAP` carries **less** than its
  share (−46%).
* Alpha's predicted RB1 finishes at **median rank 9** and is the true RB1 in **10.1%** of weeks;
  it scores 20.6 against the true RB1's 35.0.
* Misses are **not predictable**: E1 AUC **0.4875**, permutation p95 0.5453.

---

## 5. WR forensics

The worst position in the phase, and the one with the largest cliff: **−0.0800** (CI [−0.0999,
−0.0607]), 15 weeks better and 64 worse, −0.0720 to −0.0868 across LOSO folds, −0.0873 in
Half-PPR.

* **42.9%** of Alpha's WR top-10 slots are busts — nearly half.
* Missed finishers sit at **median predicted rank 29**, with a real deep tail: **30.0%** come
  from beyond predicted rank 40, three times RB's share.
* `HIGH_SNAP` carries **59.0%** of WR missed regret against a 32.8% population share (**+80%**),
  and `HOT_L3` **36.4%** against 19.5% (**+86%**). Both are defined by features Alpha already
  holds and weights at 16.7% and 9.5% of model gain.
* `ELITE_PRIOR_SEASON` shows the largest relative lift in the phase: **+133%**.
* Alpha's predicted WR1 finishes at median rank 12 and is the true WR1 in **6.3%** of weeks.
* Misses are **not predictable**: E1 AUC **0.4957**, permutation p95 0.5467.

WR is also where Alpha loses to the *trivial* season-to-date baseline at precision@5 (W4's −0.0304
finding, reproduced here).

---

## 6. TE forensics

**TE is a different animal, and the pre-registered prediction that it was not was wrong.**

* **No cliff**: capture@10 −0.0096, CI [−0.0289, +0.0096], 38–41 weeks. Null in every LOSO fold
  (−0.0030 to −0.0162) and in Half-PPR (−0.0165).
* At depths 20 and 25 TE is **significantly better** than its own null (+0.0249, +0.0245).
* Only **22.5%** of its top-10 slots are busts, the best of the three.
* Missed finishers sit at **median predicted rank 20**, and **53.0%** were already in Alpha's
  11–20 — the shallowest miss distribution of any position.
* TE has the **highest** conditional top-24 correlation (0.3219 against RB's 0.2618 and WR's
  0.2007) and retains **2.26×** the null's top signal.
* It is the only position where misses are predictable at all: E1 AUC **0.5872** against a
  permutation p95 of 0.5551 — above chance, but modest, and on 460 test rows.

TE's lower headline correlation is a consequence of its **smaller scoring scale** (mean 5.70
against RB's 8.12), not of a distinct failure mode. On the product metric it is the healthiest of
the three boards.

---

## 7. Player-archetype results

Cohort share of missed top-10 points against share of players, 79 weeks, week as the unit of
replication. Relative lift; `*` = CI on the lift excludes zero.

| cohort | RB | WR | TE | class |
|---|---:|---:|---:|---|
| `ELITE_PRIOR_SEASON` | **+70%\*** | **+133%\*** | **+52%\*** | B (partly proxied by A) |
| `HIGH_SNAP` | −46%\* | **+80%\*** | +41%\* | **A** |
| `HOT_L3` | +42%\* | **+86%\*** | −14% | **A** |
| `VOLATILE_ROLE` | +22%\* | −9%\* | −2% | A |
| `OPPORTUNITY_UP` | +36%\* | +45%\* | +27%\* | A |
| `OPPORTUNITY_DOWN` | +10% | +26%\* | +35%\* | A |
| `LOW_SAMPLE` | −27%\* | −24%\* | −34%\* | A |
| `RETURNING` | −21%\* | −34%\* | −48%\* | B |
| `ROOKIE` | −2% | −26%\* | −12% | B |
| `TEAM_CHANGE` | −43% | −87%\* | −56% | B\* |

**Every cohort that clears the +50% materiality lift is a cohort of players Alpha already ranks
highly**, and the two that clear it at WR are defined by features already in the model. **Every
cohort representing a player Alpha cannot see well — new, returning, rookie, moved — carries
*less* regret than its population share, not more.**

*Interpretive limit, stated rather than buried:* a cohort of better players will naturally supply
more of the realized top-10 and therefore more of the missed regret, so a positive lift is not by
itself proof of model failure. That is precisely why the direction of the result matters: the
cohorts a "missing information" story predicts would be *elevated* are the ones that are
*depressed*.

---

## 8. Role-change results

The highest-priority hypothesis going in, and it does not survive.

Continuous, pre-cutoff measures, tested as the week-level difference in mean top-10 regret
between the top and bottom tercile:

| | RB | WR | TE |
|---|---|---|---|
| `opportunity_delta` (last game vs prior 3) | +0.345 [−0.130, +0.823] | −0.211 [−0.591, +0.160] | +0.040 [−0.389, +0.467] |
| `snap_delta` | +0.374 [−0.073, +0.829] | +0.147 [−0.170, +0.473] | +0.347 [−0.027, +0.720] |
| `weeks_since_last_game` | −0.371 [−0.855, +0.094] | −0.003 [−0.316, +0.311] | **−0.655\*** |

**Not one is significantly positive at any position.** The only significant result is *negative*:
returning TEs carry **less** missed regret.

The quintile cohorts tell a subtler and consistent story: `OPPORTUNITY_UP` **and**
`OPPORTUNITY_DOWN` are *both* elevated (+36%/+10% RB, +45%/+26% WR, +27%/+35% TE). It is the
**magnitude** of role change that is associated with regret, not its direction — which is exactly
why the high-minus-low tercile difference is null. That is a real finding about the shape of the
association, and it is also why role change is not a directional signal a feature could exploit
straightforwardly.

`TEAM_CHANGE` is the cleanest refutation of the structural worry: the lag-3 window crosses
seasons, so a player who changes team "looks like his old self" — and players who changed team
carry **43–87% less** regret than their population share. The cohort is tiny (1.1–1.4% of
player-weeks), which is itself the answer: it is too rare to matter.

---

## 9. Injury / availability results

**The nflverse injury file cannot support a Friday-morning feature at all**, and that is the
phase's most consequential data finding.

It holds **exactly one row per (season, week, player)** — the *final* state of that week's report
— so filtering on `date_modified` **deletes** a row rather than rewinding it. In 2023, 75.5% of
rows were last edited on a **Friday**. Under the conservative **STRICT** variant
(`date_modified < cutoff`), usable coverage is:

| | STRICT coverage | FRIDAY coverage | FRIDAY missed-regret share | population share |
|---|---:|---:|---:|---:|
| RB | **0.2%** | 4.7% | 0.034 | 0.047 |
| WR | **0.2%** | 5.3% | 0.047 | 0.053 |
| TE | **0.2%** | 3.2% | 0.041 | 0.032 |

Even under the permissive FRIDAY variant, a player carrying an Out/Doubtful/Questionable
designation accounts for **no more of the missed top-10 regret than his share of the population**.
The designation is an *availability* signal, exactly as W1 insisted it be kept, and availability
is not where the top-of-board points are lost.

**Teammate injury** — the mechanism by which one player's absence creates another's opportunity —
is the only part with any signal, and it is small: RB missed-regret share 0.158 against a 0.117
population share (+35%), WR 0.243 against 0.226 (+8%), TE 0.104 against 0.111 (−6%). Only RB is
elevated, and it falls well short of the +50% bar.

**2025 is excluded entirely**: its injury file has no `date_modified` column, so no cutoff can be
applied. It is dropped and reported, never imputed.

---

## 10. Depth-chart results

Joined for 90.0–92.9% of player-weeks, 2021–2024. **2025's depth chart is a different, week-less
shape** — daily `dt`-timestamped snapshots, 219 dates from 2025-08-03, with `pos_rank` instead of
`depth_team` — so it is the only season with a *real* timestamp and the only one W5 cannot use.

Using the **previous** week's chart (the current week's is Class C — no timestamp exists for
2015–2024):

| prior depth | RB share of players / missed regret | WR | TE |
|---|---|---|---|
| **1 (starter)** | 39.4% / **62.0%** | 54.9% / **83.1%** | 48.3% / **65.5%** |
| 2 | 33.6% / 32.1% | 36.2% / 15.5% | 33.7% / 25.4% |
| 3 | 27.0% / 5.9% | 8.9% / 1.3% | 18.0% / 9.1% |

**The missed points come overwhelmingly from listed starters**, and Alpha already puts them in its
top 10 — 555 of ~790 RB slots, 585 of ~790 WR slots, 556 of ~790 TE slots go to prior-week depth-1
players. Of those, **41.7% of WR depth-1 slots still bust.**

A depth-chart feature would tell Alpha something it has already inferred. The failure is *inside*
the starter group.

---

## 11. Team-environment results

Alpha already holds the *level* of the lagged team environment (`team_epa_avg_last3`,
`team_plays_avg_last3`, `team_pass_rate_avg_last3`), which carry 1.3–9.6% of model gain and only
matter for QB. W5 tested the *change*, which a tree on the level alone cannot see:

`team_epa_delta`, high-minus-low tercile of top-10 regret: RB −0.010 [−0.498, +0.470],
WR +0.015 [−0.336, +0.371], TE −0.130 [−0.565, +0.299], QB −0.871 [−1.929, +0.149].

**Null at every position.** The existing lagged representation is not obviously insufficient, and
nothing here justifies a team-environment phase.

---

## 12. Matchup results

Opponent identity is the cleanest **Class B** signal in the repository — the schedule is fixed
months ahead, so no timestamp question arises, and Alpha uses none of it.

`opponent_pa_prior` (the opponent's average points allowed to that position over strictly prior
weeks of the same season, minimum 3 weeks), high-minus-low tercile of top-10 regret:

| | difference | 95% CI | weeks |
|---|---:|---|---:|
| RB | **+0.516\*** | [+0.040, +0.989] | 70 |
| WR | **+0.441\*** | [+0.125, +0.755] | 70 |
| TE | +0.348 | [−0.061, +0.766] | 70 |
| QB | **+1.478\*** | [+0.348, +2.614] | 70 |

Real and significant at RB, WR and QB: the board misses more points among players facing weak
defences. **But the magnitude fails the materiality bar.** Sized as points per week (E2,
exploratory):

| | weak-D tercile | strong-D tercile | gap | as a share of the position's total missed regret |
|---|---:|---:|---:|---:|
| RB | 51.2 pts/wk | 37.4 pts/wk | +13.8 | **10.1%** of 137 pts/wk |
| WR | 59.4 | 49.1 | +10.3 | **6.2%** of 166 pts/wk |
| TE | 29.4 | 25.2 | +4.2 | **5.0%** of 84 pts/wk |

Even a *perfect* exploitation of this association addresses at most a tenth of the missed regret,
and that is an association, not a recoverable quantity. Matchup is a legitimate future candidate;
it is not the bottleneck, and elevating it on statistical significance alone is the mistake §14
was written to prevent.

**Vegas and weather are absent from every ingested source.** Class C — a data-acquisition item,
not a modelling recommendation. W1's finding stands unchanged and W5 spent no further effort on it.

---

## 13. Model-architecture forensics

Verified against source, not documentation.

`CatBoostRegressor(iterations=200, depth=4, learning_rate=0.05, loss_function="MAE",
verbose=False, random_seed=42)`, per position, on 11 features, target
`target_fantasy_points_ppr`, `fillna(0.0)`, `MIN_TRAINING_ROWS = 50`. Training rows 2015–2024:
QB 6,220 · RB 14,807 · WR 23,302 · TE 11,611.

**The model is refit once per season and never sees a single week of the season it predicts.**
Week 18 of 2024 is predicted by a model whose newest training row is from 2023. In-season
information reaches the prediction only through the features.

**Feature gain is dominated by two "how good has he been lately" columns:**

| | QB | RB | WR | TE |
|---|---:|---:|---:|---:|
| `fp_ppr_avg_season_to_date` | 21.1 | **26.6** | **28.4** | **23.6** |
| `snap_pct_avg_last3` | **28.1** | **30.2** | 16.7 | 14.5 |
| *those two combined* | **49.2** | **56.8** | **45.1** | **38.1** |
| team environment (3 features) | 19.0 | 5.4 | 3.7 | 7.3 |

**No opponent, no injury, no depth chart, no rest, no market feature of any kind.** Missing-data
handling disadvantages no position (lag-3 NULL rates 1.89–2.18%, season-to-date 9.73–12.32%,
near-identical across positions).

Two structural properties of the panel, both verified in SQL:

* the lag-3 window is `PARTITION BY player_id` — **not** `(player_id, season)` — so week 1 of a
  season is described by the last three games of the previous one;
* `player_week_stats` has a row only when a player appeared, so "last 3 games" means the last
  three *appearances*, which for an injured player can span two months.

§8 tested whether either costs anything measurable at the top of the board. Neither does.

**Is the architecture itself the cliff?** W5 cannot answer that without training a variant, which
it may not do. What it can say is that the cliff is *systematic* with respect to the model's own
dominant features (§7), which is the signature of a representation problem rather than a
missing-information one — and §25 turns that into a falsifiable experiment.

---

## 14. Regression / ceiling analysis

Predicted against realized over the evaluated universe:

| | mean P | mean R | sd P | sd R | **sd ratio** | p90 P | p90 R | p99 P | p99 R | max P | max R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RB | 6.85 | 8.12 | 4.97 | 8.14 | **0.610** | 13.78 | 19.71 | 19.15 | 33.47 | 22.79 | 55.40 |
| WR | 6.38 | 7.60 | 4.50 | 7.77 | **0.580** | 13.17 | 18.60 | 15.76 | 32.22 | 17.82 | 55.60 |
| TE | 4.53 | 5.70 | 3.27 | 6.04 | **0.541** | 9.46 | 13.90 | 13.62 | 26.32 | 15.85 | 43.30 |

Alpha's predicted #1 finishes at **median rank 9 (RB) / 12 (WR) / 5 (TE)** and is the week's true
#1 in **10.1% / 6.3% / 16.5%** of weeks, scoring 20.6 / 19.2 / 15.9 against the true #1's
35.0 / 35.9 / 26.3.

**This is compression, and D112 already established it is the wrong thing to fix.** W4 found the
predictions **conditionally** well-calibrated (OLS slopes 1.0144 / 1.0129 / 1.0250) while
**marginally** compressed, and that four pre-registered rescalings all failed. A monotone
rescaling cannot change any ranking.

The pre-registered amendment A1 tested the natural follow-up — that **MAE loss fits the
conditional median** while the top-of-board metric rewards the **mean** of a right-skewed outcome.
`mean(realized) − median(realized)` by predicted decile:

| decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RB | +1.52 | +1.26 | +1.51 | +1.73 | +1.81 | +1.93 | +1.27 | +1.28 | +1.40 | +0.57 |
| WR | +1.38 | +1.26 | +1.50 | +1.52 | +1.46 | +1.61 | +1.28 | +1.30 | +1.07 | +1.42 |
| TE | +1.74 | +0.56 | +1.14 | +1.32 | +0.97 | +1.33 | +1.16 | +0.99 | +1.10 | +1.02 |

**Essentially flat, so the hypothesis is not supported and was dropped** — a near-constant
additive offset cannot reorder anything, which is W3's own finding. Recorded rather than quietly
abandoned.

What *does* vary enormously across the predicted range is **volatility**. `P(realized ≥ 2 ×
predicted)` falls from **41.5% in RB's lowest predicted decile to 5.6% in its highest** (WR 46.2%
→ 10.4%, TE 35.4% → 8.2%), and realized sd rises from 3.31 to 8.88 at RB. The players Alpha ranks
highest are the *least* likely to multiply their projection; the ones it ranks in the middle are
the most likely. With forty-odd players below its top 10 each carrying a non-trivial chance of a
huge week, most of the true top 10 is drawn from outside Alpha's. **Alpha ranks by floor and the
metric is decided by ceiling.**

---

## 15. Player-level regret

A week's top-K capture shortfall is **exactly** additive over players — verified to 1 × 10⁻⁹ on
every one of 316 cells × 4 depths (gate G8), so a cohort's contribution is a fact about the week,
not a regression estimate.

| | missed players (79 wk) | total missed | mean per miss | top-decile share |
|---|---:|---:|---:|---:|
| RB | 480 | 11,026 pts (139.6/wk) | 23.0 | 15.0% |
| WR | 543 | 13,417 pts (169.8/wk) | 24.7 | 14.8% |
| TE | 434 | 6,566 pts (83.1/wk) | 15.1 | 16.7% |

**Regret is not driven by a handful of freak outliers** — the top decile of misses carries only
15–17% of the total. It is broad and structural.

Where the missed top-10 finishers sat on Alpha's board:

| | median predicted rank | 11–20 | 21–40 | > 40 |
|---|---:|---:|---:|---:|
| RB | 22 | 44.6% | 45.2% | 10.2% |
| WR | 29 | 30.8% | 39.2% | 30.0% |
| TE | 20 | 53.0% | 33.4% | 13.6% |

And the reverse direction — how often Alpha's own top-10 slot is a bust (finishes outside the
realized top-24): **RB 26.5%, WR 42.9%, TE 22.5%.**

---

## 16. Information-class decomposition

| candidate | class | share of missed top-10 regret | verdict |
|---|---|---|---|
| lagged usage & form | **A** | the cohorts carrying the excess are defined by it | in the model, and mis-used |
| team environment (level) | **A** | change is null at every position | in the model |
| **opponent identity / prior points allowed** | **B** | 5.0–10.1% (tercile gap) | significant, **immaterial** |
| **prior-season rank** | B (partly proxied by A) | +52% to +133% lift | lift passes, value unquantifiable in scope |
| **teammate Out/Doubtful** | B (FRIDAY only) | RB +35%, WR +8%, TE −6% | fails the +50% bar |
| own injury designation | B (FRIDAY) / **C** (STRICT, 0.2% coverage) | ≈ population share | **fails outright** |
| depth chart, current week | **C** (no timestamp 2015–24; 2025 has no week key) | 83% of WR regret is depth-1 starters Alpha already ranks | tells the model what it knows |
| realized usage this week | **D** | — | bounds headroom only (§17) |
| Vegas lines, weather | **C** | — | absent from every source; acquisition item |

**Not one Class B candidate clears all three pre-registered materiality criteria.** Opponent is
significant and small. Prior-season rank has the largest lift in the phase but its recoverable
value cannot be estimated without fitting a model, which W5 may not do — it is carried forward as
a *secondary* candidate, not elevated.

**Only Class B may be elevated to an experiment**, and the roadmap therefore does not open an
information-acquisition phase.

---

## 17. Oracle / upper-bound results

Two ceilings, because W4's single one was unreachable by construction. `ORACLE_USAGE` ranks by
the week's **realized usage-expected points** (perfect opportunity foresight, zero conversion
foresight); `ORACLE_OUTCOME` ranks by realized points. Both are diagnostics, neither is a
candidate. Usage coverage: RB 91.3%, WR 90.1%, TE 90.6%, QB 99.9%; uncovered players keep Alpha's
own score rather than a fabricated one.

Positional capture@10, 79 weeks:

| | CF_A | ECR | ORACLE_USAGE | ORACLE_OUTCOME | **U** | **O** | **U/O** | **USAGE − ECR** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RB | 0.6901 | 0.7129 | **0.8716** | 1.0000 | **+0.1816\*** | +0.3099 | **58.6%** | **+0.1588** |
| WR | 0.6405 | 0.6725 | **0.8426** | 1.0000 | **+0.2020\*** | +0.3595 | **56.2%** | **+0.1700** |
| TE | 0.6959 | 0.7217 | **0.8875** | 1.0000 | **+0.1916\*** | +0.3041 | **63.0%** | **+0.1658** |
| QB | 0.7672 | 0.8094 | 0.8756 | 1.0000 | +0.1084\* | +0.2328 | 46.6% | +0.0662 |

Replicated in Half-PPR (U/O 56.7% / 51.5% / 56.9%).

**Perfect opportunity foresight is worth more than half of perfect foresight, and it beats the
benchmark by four to eight times the entire Alpha-vs-ECR gap.** The remaining 37–47% is
conversion — touchdowns and efficiency — and is unreachable from any pre-game information.

One asymmetry worth stating: on **precision**@10 the usage oracle recovers only **35–40%** of the
ceiling, against 56–63% on capture. Perfect opportunity gets you most of the *points* and only a
third of the exact *names*. Conversion decides precisely who tops a week; usage decides what the
week is worth.

**The ceiling is not the achievable value.** `ORACLE_USAGE` knows this week's actual targets and
carries. How much of that is forecastable on Friday is exactly what W5 could not answer and what
§24 names as the single highest-value open question.

---

## 18. What is actually explaining the top-board failure

Three findings, each independently supported, that fit together into one mechanism.

**(a) Alpha finds the right group and cannot order inside it.** Its conditional top-24 correlation
is **1.73× (RB), 1.82× (WR), 2.26× (TE)** the same-Spearman null's — it carries genuine
top-of-board signal. The top-10 finishers it misses sit at median predicted rank 20–29, and 90%
of RB's and 86% of TE's misses are inside its own top 40. 83% of WR's missed regret comes from
players who were the listed starter the previous week. This is a **discrimination** failure within
a correctly-identified pool, not a **detection** failure.

**(b) The discrimination failure is systematic with respect to the model's own dominant
features.** `HIGH_SNAP` (WR +80%) and `HOT_L3` (WR +86%) carry the excess, and those features
carry 16.7% and 9.5% of WR model gain; `fp_ppr_avg_season_to_date` and `snap_pct_avg_last3`
together carry 38–57% of gain at every position. Alpha promotes the stable, high-floor archetype
its two strongest features reward.

**(c) The top-10 is decided by ceiling, and ceiling lives in the middle of Alpha's board.**
`P(realized ≥ 2 × predicted)` falls from 41.5% to 5.6% across RB's predicted deciles. The players
most likely to multiply their projection are the ones Alpha ranks in the middle — and there are
four times as many of them.

Together: **Alpha ranks by expected floor; points-captured@10 is won by ceiling; the two diverge
precisely at the top of the board, and nowhere else.** That is why the cliff is confined to depths
5–20 and reverses by depth 50, where floor and ceiling rank players the same way.

TE escapes because its outcome distribution is the least top-heavy of the three: its true #1
averages 26.3 points against RB's 35.0 and WR's 35.9, so the gap between floor-ranking and
ceiling-ranking is smaller.

---

## 19. What is *not* explaining it

Reported as prominently as the positives, because each of these was a plausible pre-phase
hypothesis and each is now measured rather than assumed.

* **Not "the correlation collapses at the top."** Range restriction accounts for the entire drop;
  Alpha retains 1.7–2.3× a uniform ranker's top signal. The statistic that motivated the phase
  was an artefact.
* **Not missing injury information.** STRICT-variant coverage is 0.2%; even under FRIDAY, flagged
  players carry no more regret than their population share.
* **Not missing depth-chart information.** 62–83% of missed regret comes from prior-week starters
  Alpha already ranks in its top 10.
* **Not role change.** Every continuous measure is null; the only significant one is *negative*;
  `TEAM_CHANGE` players carry 43–87% *less* regret and are 1.1–1.4% of player-weeks.
* **Not missing team-environment change.** Null at every position.
* **Not matchup, at the relevant scale.** Significant at RB/WR/QB, worth 5–10% of missed regret.
* **Not irreducible variance alone.** A perfect *opportunity* ranking — no conversion knowledge —
  recovers 53–63% of the ceiling and beats ECR by 4–8× the current gap.
* **Not the MAE / median-versus-mean loss**, on the evidence tested: the mean−median gap is
  +1.0 to +1.9 and flat across all ten deciles, and a flat additive gap cannot reorder anything.
* **Not cross-position calibration** — settled by W4/D112 and untouched here.

---

## 20. Confirmatory versus exploratory findings

**Confirmatory** (pre-registered before any result, drives the decision): the cliff test and its
verdicts (§3); the oracle gaps `U`, `O`, `U/O` (§17); the cohort attribution and its materiality
bar (§7, §16); the continuous context associations (§8, §11, §12); the injury association (§9);
all robustness checks (§21).

**Exploratory** (labelled, generates hypotheses only, feeds no decision rule): **E1** miss
predictability (§4–§6); **E2** the opponent regret sizing in points per week (§12); **E3**
mid-season staleness — not separately reported, no week-within-season trend was found worth
stating; **E4** team-environment change sizing (§11); **A1** the mean−median decile table (§14),
added by dated amendment after results and reported with its negative outcome.

**§16's materiality verdicts rest on confirmatory analyses only.** No exploratory result was used
to elevate or dismiss an information class.

### 20.1 The a priori predictions, scored

Recorded in `docs/weekly/W5_PREREGISTRATION.md` §3 **before** the instruments were written,
explicitly so they could be wrong in public. Four held, three were wrong, one split.

| # | prediction | outcome |
|---|---|---|
| 1 | Most of the collapse is range restriction; **P1 returns NO CLIFF** | **SPLIT.** The range-restriction half is right and *stronger* than predicted — the null reproduces the entire drop. The NO CLIFF half is **WRONG at RB and WR** (−0.0710, −0.0800, CIs excluding zero) and right at TE |
| 2 | `ORACLE_USAGE` recovers **less than half** of the outcome oracle | **WRONG.** 58.6% / 56.2% / 63.0% on capture@10, replicated in Half-PPR. Perfect opportunity is worth more of the ceiling than predicted, which raises the priority of the runner-up in §24 |
| 3 | Role change is a real but **modest** contributor, ~1.5× | **WRONG in direction.** Every continuous measure is null; `TEAM_CHANGE` and `RETURNING` carry 21–87% **less** regret than their population share. Only the symmetric `OPPORTUNITY_UP`/`DOWN` quintiles are elevated, and by ~1.3–1.5× |
| 4 | Injury/practice explains less than expected | **RIGHT**, emphatically — STRICT coverage 0.2%, FRIDAY share equal to population share |
| 5 | Opponent explains very little and fails the bar at every position | **RIGHT on materiality** (5–10% of missed regret), **partly wrong on "very little"** — significant at RB, WR and QB |
| 6 | TE is **not** a distinct failure mode | **WRONG.** TE is the one position with no cliff, is better than its own null at depths 20–25, and is the only one whose misses are predictable at all |
| 7 | Miss-model AUC below 0.62 | **RIGHT** — 0.4875 / 0.4957 / 0.5872 |
| 8 | The decision will not be "add features" | **RIGHT** — no Class B candidate clears the materiality bar |

Predictions 1 and 6 being wrong is what makes §25's experiment RB/WR-scoped rather than universal;
prediction 2 being wrong is what makes the opportunity model a named runner-up rather than a
footnote. The errors changed the recommendation, which is the point of recording them.

---

## 21. Robustness

**Leave-one-season-out** on the cliff (capture@10), 15 recomputations:

| | −2021 | −2022 | −2023 | −2024 | −2025 |
|---|---|---|---|---|---|
| RB | −0.0787\* | −0.0699\* | −0.0668\* | −0.0711\* | −0.0686\* |
| WR | −0.0807\* | −0.0868\* | −0.0831\* | −0.0720\* | −0.0776\* |
| TE | −0.0089 | −0.0141 | −0.0162 | −0.0061 | −0.0030 |

Every RB and WR fold negative and significant; every TE fold null. No season carries the result.

**Per-depth consistency**: §3.2. The cliff is monotone in depth and reverses sign by depth 50 at
RB — the conclusion does not depend on which depth is read, and the depth at which it is largest
(5) is not the depth the decision rule uses (10).

**Half-PPR replication**: cliff RB −0.0794\*, WR −0.0873\*, TE −0.0165 (ns); `U/O` 56.7% / 51.5% /
56.9%. Both headline findings hold in the second shipped scoring format. The usage oracle is
re-scored for Half-PPR by removing the expected reception credit, using the identity W1
established for realized points — ffopportunity publishes full PPR (verified: mean |difference|
0.0124 against this repository's `fantasy_points_ppr`, versus 1.259 for Half-PPR).

---

## 22. What this means for the product

* **The weekly board's top 10 is where the product lives and where Alpha is weakest**, and the
  weakness is real rather than an artefact: 26.5% of its RB top-10 slots, and **42.9%** of its WR
  top-10 slots, are filled by players who finish outside the realized top-24.
* **The cliff is larger than the benchmark gap it sits inside.** RB's capture@10 deficit to ECR
  is −0.0228; its cliff is −0.0710. WR's deficit is −0.0320; its cliff is −0.0800. A board free of
  the cliff would sit at roughly 0.761 (RB) and 0.721 (WR) against ECR's 0.713 and 0.673. *The
  null is a reference point, not an achievable design* — nothing here promises that number is
  reachable — but it does establish that the top-of-board defect, not the overall quality gap, is
  what stands between Alpha and the benchmark at the depth the product is graded on.
* **TE already works** and should not be changed in pursuit of an RB/WR fix. A universal
  intervention risks breaking the one healthy board.
* **The product's separation of projected points from availability (W1) is vindicated**:
  injury designation explains none of the top-of-board points loss.
* Neither W3 engineering prerequisite is resolved, and §26 states which of them gates the next
  experiment.

---

## 23. W5 research decision

**Do we understand enough to justify changing the model? Yes — and the change is not the one the
phase set out expecting.**

Against the pre-registered decision framework (§14):

| rule | outcome |
|---|---|
| CLIFF **and** a MATERIAL Class B cohort → focused information phase | **not triggered** — cliff confirmed at RB/WR, but **no Class B candidate clears all three bars** |
| NO CLIFF and small `U/O` → overall-quality experiment | not triggered — there *is* a cliff, and `U/O` is large |
| errors unpredictable and no material class → treat as irreducible | **partly triggered** — E1 is at chance for RB/WR, and no class is material |
| positions differ → position-specific work | **triggered** — TE has no cliff and must be excluded from any RB/WR intervention |
| significant but small → do not elevate | **triggered** — opponent, teammate-injury, prior-season rank |

**Decision: no information-acquisition phase. The next experiment targets how the objective is
represented, not what the model is fed, and it is scoped to RB and WR.**

The third rule is triggered but does *not* mean "stop". E1's chance-level AUC says a *per-player*
miss is unpredictable; it does not say the *systematic* selection bias in §18 is unfixable — that
bias is a property of the ranking function, visible in aggregate across 79 weeks, and a
per-player classifier at n=460 is not the instrument that would detect it.

---

## 24. The single highest-value W6 question

> **Alpha ranks by expected floor; the top of the board is won by ceiling. Does training the same
> model on an upper quantile of the outcome instead of its median recover the top-of-board
> capture that §3 shows it is losing — at RB and WR, without damaging TE or the deep board?**

Chosen over the alternatives because it is the only candidate that is **large, cheap, falsifiable
and already evidenced**: the cliff is worth more than the entire gap to ECR (§22), the information
needed is already in the model (§18b), and the experiment changes one argument.

**The runner-up, named explicitly**: a two-stage *opportunity* model — predict the week's targets
and carries, then convert to points — because `ORACLE_USAGE` shows 53–63% of the ceiling and
+0.16 to +0.21 over ECR lives there (§17). It is the bigger prize and the more expensive test, and
its decisive unknown is *how much of usage is forecastable on Friday*, which W5 did not measure.
**That measurement should precede the model**, and it is a cheap study in its own right: fit
nothing, just correlate strictly-prior usage features against realized usage, the way §2.6 did for
points.

---

## 25. Proposed W6 experiment design

**Pre-registration to be written and committed before execution, as W2–W5 were.**

| | |
|---|---|
| **Hypothesis** | Alpha's top-of-board deficit at RB and WR is caused by ranking on a floor-optimal target. Training the identical model on an upper quantile of the outcome improves positional capture@10 relative to the frozen control. |
| **Treatment** | `CatBoostRegressor(loss_function="Quantile:alpha=τ")` for `τ ∈ {0.6, 0.7, 0.8}` — three arms, fixed now, **no sweep**. |
| **Control** | the frozen W3/W5 `CF_A`, byte-reproducible from `reports/weekly/w5_results.json`. |
| **Frozen** | the 11 features, the target column, `iterations=200`, `depth=4`, `learning_rate=0.05`, `random_seed=42`, the per-position split, the walk-forward window `[2015, S−1]`, `fillna(0.0)`, the universe, the cutoff, the metric suite. **One argument changes.** |
| **Scope** | RB and WR confirmatory; **TE and QB reported as guard rails, not targets** — §6 shows TE has no cliff and a universal change could break it. |
| **Historical scope / cutoff** | identical to W5: 79 weeks, 2021–2025, Full PPR primary, Half-PPR replication, Friday cutoff. |
| **Leakage rules** | unchanged and re-gated by `w5_validity_gates.py`, which is position- and model-agnostic: G1 causality, G2 no-outcome-leak, G3 universe, G7 already-played, G10 determinism. |
| **Primary metric** | positional **capture@10**, paired within week, 95% bootstrap CI over 79 weeks (10,000 resamples, seeds 0–9). |
| **MDE** | 0.0196–0.0206 on capture@10 at n=79 (measured in W5, not assumed). |
| **Statistical test** | paired bootstrap CI plus Wilcoxon signed-rank and win/loss counts, as in W2–W5. |
| **Success** | CI excludes zero **and** the effect is ≥ **+0.02** at RB **or** WR — half the cliff, and above the MDE — **and** TE's capture@10 does not degrade with a CI excluding zero **and** capture@50 does not degrade with a CI excluding zero. |
| **Failure** | every arm's CI contains zero, **or** the best arm is below +0.02, **or** any arm buys capture@10 at the cost of a significant loss at TE or at depth 50. A failure is reported as a failure and closes the quantile line, exactly as D112 closed calibration. |
| **Robustness** | leave-one-season-out; per-depth 5/10/20/25/50; Half-PPR replication; the copula-null cliff test re-run on the treated board, which is the direct check that the *mechanism* moved and not just the metric. |
| **Production constraints** | research-only. The treatment trains a variant under a research model name; `WEEKLY_PROJECTION_BASE_MODEL` and every production path stay untouched until a separate, later decision. |

**The mechanism check is what makes this falsifiable rather than a metric hunt.** If the quantile
arms improve capture@10 *without* shrinking the copula-null cliff, §18's mechanism is wrong and
the improvement is something else — and that must be reported as such.

---

## 26. Engineering prerequisites

Both W3 defects remain open and untouched. W5 investigated only whether they constrain W6.

**(1) The served evidence layer's post-Friday injury leak.** **Does not gate W6.** §9 shows the
injury signal is worth nothing at the top of the board, and the proposed experiment reads no
injury data. It remains a live correctness defect in the served path and should be fixed on its
own merits — and W5 adds a reason it cannot simply be "fixed by filtering": under a genuine
pre-Friday cutoff the nflverse file retains **0.2%** of its rows, so the layer needs a different
source, not a stricter predicate.

**(2) Alpha cannot produce a true Friday board.** **Gates production, not W6.**
`player_week_features` exists only for players who appeared, so the universe is defined by who
played. Every system in W5 is scored on that same universe, so the comparison is valid — but no
result here transfers to a live Friday board until the eligibility architecture is fixed. W6 can
run under the same limitation; **shipping cannot.**

**(3) New: the depth-chart schema break.** 2025's `nflverse/depth_charts` is a different, week-less
shape. It is the only season with a real timestamp and the only one unusable by week. If a future
phase wants depth-chart features, that bridge is the acquisition work — but §10 says it should not
want them.

---

## 27. Test / lint / reproducibility status

### 27.1 Validity gates — all ten pass, and one of them failed first

| gate | check | result |
|---|---|---|
| **G1** causality | prior-window rows at or after the ranked week | **0** |
| **G2** no-outcome-leak | context values that move when the ranked week's outcomes are deleted | **0** |
| **G3** universe | boards whose player set differs from the cell's | **0** |
| **G4** position | players on the wrong positional board | **0** |
| **G5** oracle | cells where `ORACLE_OUTCOME` is not perfect | **0** |
| **G6** no-ECR | cells where Alpha's order needs more than its predictions | **0** |
| **G7** already-played | evaluated players whose team had kicked off | **0** |
| **G8** regret-exact | (cell × depth) where regret ≠ shortfall, over 316 cells × 4 depths | **0** |
| **G9** null-calibration | worst \|achieved − target\| Spearman over 30 real cells | **7.66 × 10⁻⁶** |
| **G10** determinism | SHA-256 of the output JSON, two full runs | **identical** |

**G10 failed on the first complete run** — two runs produced different digests — and per the
pre-registration's own rule no result was interpreted until it was diagnosed and fixed. The cause
was a single expression in `aggregate_cohorts`: `dict.keys() & dict.keys()` returns a **set**,
whose iteration order for string keys depends on `PYTHONHASHSEED` and therefore varies between
processes, and `noise._bootstrap_mean_ci` indexes its input **by position**. The cohort *lift*
confidence intervals — the numbers §7's significance marks are read from — differed on every run.
Every other intersection in the package was already `sorted(set(a) & set(b))`; this one was not.

The fix went further than the one line. A `_by_week` helper now puts **every** per-week list into
canonical week order before it reaches the bootstrap, so the property is structural rather than
incidental, and `TestAggregationIsOrderInvariant` pins it in milliseconds rather than after two
twelve-minute runs. **Post-fix, every significance mark in §7 is unchanged and every headline
number is identical** (cliff −0.0710 / −0.0800 / −0.0096; `U/O` 58.6% / 56.2% / 63.0%) — the
defect moved intervals, not conclusions, which is why it had to be found by a gate rather than by
reading the results.

### 27.2 Defects this phase found in its own instruments

Six, none of them leakage, every one fixed before the affected number was read:

1. **The copula null landed ~0.017 below its target Spearman**, because a tie-corrected Spearman
   against a heavily tied outcome is attenuated. That bias would have handed the null a *worse*
   board than Alpha and flattered this phase's own pre-registered answer. The latent correlation
   is now bisected per cell against that cell's own tie structure; achieved error 7.66 × 10⁻⁶.
2. **A conditional correlation was being compared across incompatible scales** — Alpha's
   compressed point predictions on one side, the null's uniform *rank* on the other — which made
   the null look five times worse at the top purely through the mismatch. Fixed with a scale-free
   statistic plus a value-curve transplant.
3. **`over_promotion` was conceptually backwards**: negative regret is points the board *did*
   capture, and a bust who scores 0.0 carries no regret at all. Renamed `slot_credit`.
4. **A `row_number()` left 13 TEs tied on exactly 0.0 points** (caught by G2), so prior-season
   rank was plan-dependent. Given a `player_id` tiebreak.
5. **A `stddev_samp` whose input order the planner could vary** (caught by G2). Replaced with an
   ordered list and a fixed-order reduction.
6. **The Half-PPR usage oracle reported `U = +0.0000` exactly** — caught by reading a result that
   could not be true. The usage load was gated on the flag that switches off the cohort work, and
   `load_usage_points` was not scoring-format aware. ffopportunity publishes **full PPR**
   (verified: mean absolute difference 0.0124 against this repository's `fantasy_points_ppr`,
   versus 1.259 for Half-PPR and 2.512 for standard), so a Half-PPR board now has the expected
   reception credit removed by the identity W1 established for realized points.

### 27.3 Reproduction and repository

* **W3 reproduces exactly**: 46,756 numeric leaves of 49,003, maximum absolute difference **0**,
  key sets identical.
* **W4 reproduces exactly**, re-verified after every W5 change: 126,844 numeric leaves of 129,113,
  maximum absolute difference **0**, key sets identical.
* **1,567 → 1,611 tests pass**, 44 deselected (W5 adds 44: 21 in `test_weekly_topboard.py`, 21 in
  `test_weekly_regret_context.py`, 2 in `test_w4_flex_forensics.py`).
* `make lint` clean, **both** halves (`ruff check` and `ruff format --check`).
* **Production diff EMPTY.**

**Reproduce:**

```
uv run python scripts/research/w5_topboard_forensics.py  --out reports/weekly/w5_results.json
uv run python scripts/research/w5_validity_gates.py            # non-zero if any gate fails
uv run python scripts/research/w5_miss_predictability.py --out reports/weekly/w5_e1.json
```
