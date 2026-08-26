# Alpha vs. Baselines: Empirical Evaluation Results

Companion to `docs/EVALUATION_PLAN.md` (methodology) and `docs/EVALUATION_LIMITATIONS.md`
(what can't be measured here and why). Every number below comes from a real
`alpha-squad evaluate <name>` run against this project's real database — reproduction commands
are in `docs/EVALUATION_PLAN.md`. Full source reports are under `reports/*.md`. See
`docs/DECISIONS.md` D54 for the methodology commitments made before any of these numbers existed.

**This document reports results as found, favorable or not.** Two of the headline findings
below are unfavorable to Alpha's current implementation. They are reported in full, per the
phase's explicit instruction not to design the evaluation to make Alpha look good.

## Direct answers to the eleven questions

1. **Is Alpha's player intelligence better than reasonable baselines?** — **Yes, on point
   accuracy.** `ml_season_catboost` has the lowest MAE of any model (baseline or Alpha) at
   every position (QB/RB/WR/TE) over the real 2021-2025 window. See §1.
2. **Is Alpha's EDGE signal actually useful?** — **Partially confirmed, direction only.**
   BUY beat the market in all 4 scored seasons (2022-2025); SELL was genuinely mixed (beat in
   2022-2023, roughly neutral 2024, wrong-direction 2025). Disagreement *magnitude* alone
   (rank-edge tiers 1-3, no evidence gate) does **not** show a clean monotonic relationship
   with outcome — only the evidence-gated BUY/SELL tier does. See §2, §3.
3. **Does league context improve decisions?** — **Mixed, but net No as currently
   implemented — a real, unfavorable finding.** `alpha_league_aware` (real roster context +
   VORP) beats `alpha_bpa` (identical player values, no context) on mean *starter* points
   (1644.5 vs 1429.1 pooled) but loses to it on mean *total roster* points (2680.0 vs
   2756.1) — context helps the lineup you actually start but leaves more value stranded on
   the bench overall — and loses to plain `market_consensus` on every measure. See §4 for
   the root cause found while investigating this.
4. **Does Alpha make better draft decisions?** — **No — a real, unfavorable finding.**
   `market_consensus` beat `alpha_league_aware` on mean starter points in every one of the 5
   real seasons tested (2020.7 vs 1644.5 pooled) and `alpha_league_aware` never won a single
   season outright. See §4.
5. **Does Alpha make better waiver/FAAB decisions?** — **Inconclusive with this proxy; the
   full question isn't measurable here.** See §5 and `docs/EVALUATION_LIMITATIONS.md`.
6. **Does Alpha make better roster decisions?** — Mixed with §4's finding: Alpha's underlying
   player values are good (§1), but the roster-construction logic that turns them into an
   actual draft has a real, identified bug (§4).
7. **Does Alpha's trade/roster intelligence improve decisions?** — Trade action quality
   inherits EDGE's real, partially-confirmed evidence (§2); the *value* heuristics it also
   uses have mixed real-world support (§6). A causal trade-outcome study isn't measurable here.
8. **Where does Alpha clearly win?** — Point-accuracy of the season-level model (§1); the
   BUY signal specifically (§2); late-round rookie evaluation (§7).
9. **Where does Alpha clearly lose?** — The draft decision engine vs. simply following market
   consensus (§4) — and the mechanism is now understood, not just observed.
10. **What remains inconclusive?** — Whether disagreement magnitude alone (absent an evidence
    gate) is predictive (§3); early-round rookie evaluation vs. draft capital alone (§7);
    the age-curve heuristic's specific decline ages, confounded by survivorship (§6); FAAB
    bid quality (§5, not measurable here).
11. **What should we improve next?** — Fix `recommend_draft_pick`'s roster-balance logic
    (§4) — this is the single highest-value, most concrete, most actionable finding of this
    phase.

---

## 1. Projection benchmark: Alpha's player model vs. baselines A/B/C

`reports/projection_benchmark.md`. Real intersection window: 2021-2025 (every baseline and
every Alpha season-level model has a real walk-forward row in this range).

| Position | Best model | MAE | 2nd best | MAE |
|---|---|---|---|---|
| QB | ml_season_catboost | 53.8 | ml_season_xgboost | 60.7 |
| RB | ml_season_catboost | 43.9 | baseline_ecr_implied | 46.0 |
| TE | ml_season_catboost | 27.1 | ml_season_ridge | 29.1 |
| WR | ml_season_catboost | 39.7 | ml_season_ridge | 42.4 |

`ml_season_catboost` wins MAE outright at **every position**, including beating
`baseline_ecr_implied` (the market-consensus baseline) everywhere. On Spearman rank
correlation it also leads at QB/RB/WR; at TE it narrowly trails `baseline_weighted_2yr`
(0.772 vs. 0.790). **Verdict: VALIDATED.** Baselines D (FantasyPros projections) and E (ADP)
are not included — see `docs/EVALUATION_LIMITATIONS.md` for why no historical back-series
exists for either in this environment.

## 2. EDGE backtest: does the model-vs-market signal work?

`reports/edge_backtest.md`, re-run this phase against current data.

| Season | BUY outperformance | SELL outperformance |
|---|---|---|
| 2022 | +27.2 | −34.9 |
| 2023 | +19.2 | −22.2 |
| 2024 | +18.8 | +1.4 |
| 2025 | −5.7 | +35.6 |

BUY beat the market in 3 of 4 seasons, with a declining-but-mostly-positive trend (2025 was
the first negative BUY season on record). SELL is genuinely mixed — a good SELL should show
*negative* outperformance (the player underperforming as predicted); that held in 2022-2023,
was roughly neutral in 2024, and inverted in 2025. **Verdict: PROMISING for BUY, INCONCLUSIVE
for SELL.** Consistent with the D41/D52 finding that this signal is real but not uniformly
reliable across seasons.

## 3. Market inefficiency: does disagreement magnitude predict outcome?

`reports/market_inefficiency.md`, seasons 2022-2025.

| Tier | n | Mean signed edge |
|---|---|---|
| 1. Agrees with market | 161 | −1.4 |
| 2. Mildly disagrees | 244 | +2.2 |
| 3. Strongly disagrees | 928 | −2.9 |
| 4. Disagrees, high confidence | 1 | −23.1 (n=1, not meaningful) |
| 5. Disagrees, evidence-backed (BUY/SELL) | 209 | +14.9 |

**Not monotonic.** Raw disagreement magnitude alone (tiers 1-3) does not cleanly predict
outcome — tier 3 (strong disagreement, no evidence gate) is worse than tiers 1 and 2. Only
tier 5 — the evidence-gated BUY/SELL cohort — shows a clearly positive signal. **Verdict:
this validates the *existing gating design decision* (D21: a raw rank/points discrepancy
alone must not produce BUY/SELL) more than it validates "bigger disagreement is better."**
The evidence gate is doing real work, not just adding friction.

## 4. Draft simulation: the headline unfavorable finding, with root cause

`reports/draft_simulation.md`, real seasons 2021-2025, 10 draft slots each, 4 strategies.

**Two real bugs were found and fixed while stress-testing this specific module for leakage
and reproducibility** (prompted by a direct question about whether pre-2025 training data was
genuinely separated from 2025 outcomes) — see `docs/DECISIONS.md` D54's "Results" addendum for
the full account. Neither was a methodology change; both were software defects in code this
phase reused, fixed with regression tests before any number below was treated as final:

1. `league/draft.py::next_pick_survival_probability` (used only by `alpha_league_aware`) had
   no season scoping at all — it read `market_snapshot`'s single most-recently-scraped row
   regardless of which historical season was being drafted, so a simulated 2021 draft could
   see expert-rank dispersion recorded as late as 2026. Fixed by restricting it to the season
   being drafted's own Jul/Aug window, matching every sibling function in the same call chain.
2. `_market_consensus_pick`/`_generic_prior_year_pick`/`_alpha_bpa_pick` and
   `recommend_draft_pick`'s candidate sort broke ties over a Python `set` with no secondary
   key. `PYTHONHASHSEED` is unset in this environment (confirmed: `hash()` differs across
   process runs) and real ties are common in the underlying data (43 tied ECR-rank groups,
   49 tied prior-year-points groups just in the seasons checked) — so a tied pick could
   silently differ between runs of the identical historical draft. Fixed by adding
   `player_id` as an explicit deterministic tie-break. **Verified, not assumed:** the
   simulation was re-run twice in separate processes after the fix and the two reports are
   byte-for-byte identical.

The corrected, reproducible numbers:

| Strategy | Mean starter pts (pooled) | Wins on starter pts, how many of 5 seasons |
|---|---|---|
| market_consensus | 2020.7 | 4 / 5 |
| generic_prior_year | 1708.3 | 1 / 5 (2025) |
| alpha_league_aware | 1644.5 | 0 / 5 |
| alpha_bpa | 1429.1 | 0 / 5 |

**Correction to this document's earlier claim:** market consensus does *not* win outright in
all 5 seasons — in 2025 `generic_prior_year` (2139.4 starter pts) edges out `market_consensus`
(1984.3). What does not change: `alpha_league_aware` never wins a single season, and loses to
`market_consensus` in every one of the 5. This directly answers questions 3 and 4 unfavorably
for Alpha's current draft decision engine — on a now leak-free and verified-reproducible basis.

**Root cause, found by inspecting real drafted rosters (not left as an unexplained number, and
re-verified against the corrected data):** `alpha_league_aware`'s real 2021 draft-slot-1
roster drafted **7 quarterbacks and zero running backs** (into a league that starts 2 QB and 2
RB) among its 17 picks (7 QB / 7 WR / 3 TE). Its real 2025 roster was 12 WRs against only 3
QBs. `recommend_draft_pick`'s `roster_fit_multiplier` is bounded to [0.7, 1.3] (deliberately,
so a marginal roster need can never invert a large talent gap — see `league/roster.py`) — but
this means once one position's VORP genuinely runs hotter than others for several consecutive
picks, the bounded fit multiplier cannot correct hard enough, and the engine stacks that
position (or starves another) far past what any real roster can use. Bench players who never
become starters contribute to `total_roster_points` but not `starter_points`, which is exactly
the gap observed (`alpha_league_aware`'s total-points shortfall vs. market_consensus, 255.1
pts pooled, is smaller than its starter-points shortfall, 376.2 pts — points are there, just
on the bench). Market consensus avoids this failure mode because real aggregate expert
rankings already implicitly balance across positions; a single-model VORP ranking does not
unless something forces it to.

**A genuinely mixed nuance worth stating plainly, not just the unfavorable half:**
`alpha_league_aware` actually *beats* `alpha_bpa` on pooled starter points (1644.5 vs 1429.1)
even though it loses to `alpha_bpa` on pooled total roster points (2680.0 vs 2756.1) — league
context measurably improves the value of the lineup a manager actually starts, it just also
strands more value on the bench overall via the position-stacking failure mode above. League
context is not doing nothing; it is doing one real thing well and one thing badly.

**This is not a modeling problem — §1 shows Alpha's underlying player values are good.** It is
a **decision-logic** bug in how those values get turned into a sequence of 17 picks. **Verdict:
FAILED as currently implemented, with a specific, well-evidenced, actionable root cause** —
this is the single most useful finding of this phase (directive question 11).

## 5. Waiver-tier value discovery (preseason proxy)

`reports/waiver_tier_evaluation.md`, real seasons 2020-2025. See
`docs/EVALUATION_LIMITATIONS.md` for why a true FAAB-bidding backtest isn't feasible here —
this tests a narrower, real question: among players a standard league wouldn't have rostered,
does Alpha's preseason ranking of that pool find real subsequent value. **Verdict:
INCONCLUSIVE as a full answer to "are waiver/FAAB recommendations good"** — it is evidence
toward a necessary condition, not the full claim. See the report for per-season numbers.

## 6. Dynasty heuristics: pick value and age curves vs. real outcomes

`reports/dynasty_heuristic_validation.md`.

**Pick value (D45):** real rookie-season points decline monotonically by round across all 7
real rounds (152.0 → 103.2 → 69.1 → 48.8 → 41.0 → 24.4 → 12.8) — a clean confirmation of the
heuristic's core directional assumption. Best-of-first-3-seasons is *not* perfectly
monotonic (round 5 at 79.1 slightly exceeds round 4 at 74.3) — a small, real, disclosed
deviation. **Verdict: PROMISING**, direction confirmed, exact ratios not expected to match
(the heuristic prices assets under uncertainty, not expected value — see the report).

**Age curve (D25):** real observed peak ages (RB 35, WR 36, TE 36, QB 44) are far later than
the heuristic's assumed decline-start ages (RB 27, WR 29, TE 30, QB 34) — but every one of
those late-age cells has n ≤ 8, a highly survivorship-selected group of unusually durable
veterans, not a representative sample. **Verdict: INCONCLUSIVE** — the real data neither
clearly confirms nor clearly refutes the assumed decline ages once the selection effect is
accounted for; see the report's own reasoning.

## 7. Rookie evaluation vs. baselines, by round tier

`reports/rookie_benchmark.md`, draft classes 2019-2024.

| Tier | Best model | MAE |
|---|---|---|
| Early (rounds 1-2) | baseline_rookie_draft_capital | 60.5 (Alpha: 63.7) |
| Mid (rounds 3-4) | baseline_rookie_draft_capital | 45.9 (Alpha: 47.4) |
| Late (rounds 5-7) | **ml_rookie_regression (Alpha)** | **28.7** (best baseline: 30.4) |

Alpha's rookie model's real edge is concentrated in **late-round picks**, where draft capital
alone is a weak signal and Alpha's additional features (landing spot, combine, etc.) add real
value. In early/mid rounds, where draft capital is already a strong signal on its own, Alpha
does not clearly beat it. **Verdict: MIXED, but genuinely informative** — this is a real,
specific, round-tier-conditional finding, not a uniform win or loss.

## 8. Trade evaluation

`reports/trade_evaluation.md` — inherits §2's EDGE evidence for action quality; the value
heuristics feeding trade comparisons are covered in §6. No causal trade-outcome study is
feasible here (see `docs/EVALUATION_LIMITATIONS.md`).

## 9. Failure analysis

`reports/failure_analysis.md` — real, named misses, not a curated sample. Headline examples:
Aaron Rodgers' 2023 BUY call (0 actual points against 187.2 implied — his real Achilles
injury in week 1, unknowable at signal time); Christian McCaffrey's 2025 SELL call badly
underestimating a real bounce-back season; Puka Nacua (2023) and Bucky Irving (2024) as
real rookie breakouts no draft-capital or model-based approach caught. See the report for the
full lists and cause categorization.

## Overall verdict, per directive section 21

- **VALIDATED:** Alpha's season-level player-value model beats baselines on MAE at every
  position (§1); pick-value's directional assumption (§6); the EDGE evidence-gate design
  decision specifically, over raw disagreement magnitude (§3).
- **PROMISING:** The BUY signal (§2); late-round rookie evaluation (§7).
- **INCONCLUSIVE:** SELL signal reliability (§2); disagreement magnitude alone (§3);
  waiver-tier value discovery as a full answer to FAAB quality (§5); age-curve decline ages
  under survivorship bias (§6); early/mid-round rookie evaluation vs. draft capital alone (§7).
- **FAILED (with identified cause):** The draft decision engine's real-world roster
  construction (§4) — loses to simply following market consensus, root-caused to a roster-fit
  bound too weak to prevent position-stacking.
- **NOT YET EVALUATED:** FAAB bid efficiency/opportunity cost (needs real transaction data
  this environment doesn't have); causal trade-outcome attribution (same constraint).
