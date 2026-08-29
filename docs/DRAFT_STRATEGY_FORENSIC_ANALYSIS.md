# Draft strategy forensic analysis (post-D60)

Why the shipped 1-QB engine's headline win over consensus is not what it appears to be, what
Alpha actually does well and badly, and which failure modes are real and fixable.

Every number here was measured against the live database and the shipped code during this
phase. Where a figure contradicts an earlier document, the earlier document is cited and the
contradiction is stated explicitly rather than quietly restated.

Companions: `docs/DRAFT_OBJECTIVE_MODES.md` (what we are optimizing),
`docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md` (what to do next),
`docs/FORMAT_MIGRATION_DIAGNOSTIC.md` (the D56–D60 phase this supersedes in part),
`docs/BENCHMARK_SPEC.md` (benchmark definition), `docs/DECISIONS.md` D56–D61.

> **Update (D62):** the fair-opponent numbers in this document (§1, "−48.3, 25/50") were a
> targeted re-simulation, not the shipped benchmark code. Stage 1 of the next-phase plan has
> since shipped the fair opponent into `evaluation/draft_simulation.py` for real
> (`market_consensus_roster_aware`) and re-run it against real 2021–2025 data: **−45.4 mean
> starter points, 25/50 win rate, 95% CI [−117.1, +25.6]** — confirming this document's
> estimate to within 3 points. Read the fair-opponent numbers below as directionally and
> quantitatively correct, now with a direct measurement backing them; see D62 for the
> shipped-code figures.
>
> **Update (D63):** the diagnosis in this document was acted on and the engine changed — the
> value base is now `marginal_starter_value + VORP`, closing the fair-opponent gap from −45.4
> to **−5.6**. Two caveats on the *behavioural* figures below, which were measured on the
> pre-Stage-1.2 harness whose feasibility caps diverged from production (RB/WR capped at 3
> against production's 6):
>   * §"68% of drafts take a QB in round 2" re-measures at **92%** under the corrected caps,
>     against *both* opponent fields — so the opponent is ruled out as the cause of the
>     difference and this document's figure should not be quoted as current.
>   * The mechanism this document identifies (MSV discarding positional scarcity) is
>     **confirmed** — but its proposed remedies were wrong. Both clamping formulations
>     (`min(vorp, msv)`, and marginal starter value over replacement, called "most likely to be
>     right" in the next-phase plan) were measured and both LOST to the control. Summing the
>     two signals wins; selecting between them per-candidate does not. See D63.

---

## 0. Headline

**The documented result "Alpha beats market consensus by +165.7 starter points (+9.1%), 37/50
win rate" (D59/D60, `docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0) is an artifact of a benchmark
opponent that forfeits two of its ten starting slots.**

Against a consensus opponent that merely fills its mandatory K and DEF slots — the single
thing every real human drafter does, and the only change — **Alpha loses by 48.3 starter
points with a 25/50 (50%) win rate.** The 95% confidence interval on that margin is
[−122.2, +25.6]; it contains zero. Alpha is statistically indistinguishable from, and
point-estimate behind, a fair consensus opponent.

This does not mean the D56–D60 work was wrong. The market-series correction (D56), the K/DST
data work (D57), the format retarget and flex-aware capacity (D58) are all independently
verified and stand. What does not stand is the claim that the shipped engine outperforms
consensus, and the P1-0 closure that rested on it.

---

## 1. The benchmark opponent forfeits two starting slots

### 1.1 The mechanism

`market_consensus` in `evaluation/draft_simulation.py` picks the best available player by
preseason overall ECR rank, with no roster awareness. `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §2
and `docs/EVALUATION_LIMITATIONS.md` both name that lack of roster awareness as a known
limitation. What nobody had quantified is that in a 1-QB league with K and DEF starting slots,
the limitation is worth more than the entire measured margin.

Measured on the real `ro`/`redraft-overall` board, preseason 2024:

| position | rows | best overall ECR rank |
|---|---|---|
| RB | 1276 | 1 |
| WR | 1598 | 2 |
| QB | 497 | 21 |
| TE | 725 | 29 |
| **DST** | 271 | **155** |
| **K** | 284 | **186** |

A 16-round, 10-team draft is **160 picks**. The best kicker on the board ranks 186th overall —
**beyond the end of the draft**. The best defense ranks 155th, reachable only in the final
handful of picks and only by whichever team happens to be on the clock.

This is a real property of the FantasyPros overall board, not a data bug: the board ranks K
and DST by overall value, while every real drafter applies a positional-need override in the
last two rounds. The consensus *bot* has no such override, so it never takes them.

Measured over the 50 benchmark drafts:

| | mean K drafted | mean DST drafted | mean round of first K | mean round of first DST |
|---|---|---|---|---|
| Alpha | 1.60 | 1.10 | 8.5 | 10.0 |
| consensus | **0.00** | **0.30** | never | 75.6 (i.e. mostly never) |

### 1.2 What that is worth

Decomposing all 50 benchmark drafts' realized starter points by slot type:

| | K + DEF slots | the 8 skill slots | total |
|---|---|---|---|
| `alpha_league_aware` | **275.1** | 1715.8 | 1990.9 |
| `market_consensus` | **29.8** | 1795.4 | 1825.2 |
| **Alpha − consensus** | **+245.3** | **−79.6** | +165.7 |

**148% of Alpha's documented edge comes from two slots the opponent leaves empty. On the eight
skill slots where the competitive game is actually played, Alpha is 79.6 points behind.**

### 1.3 The fair comparison

A roster-aware consensus was simulated with exactly one change: in its last two rounds it
fills K and DEF if still empty, taking the best available *at that position* by the same ECR
rule. No hindsight, no projection access, no other behavioral change — strictly the
positional-need override a human applies.

| opponent | mean starter pts |
|---|---|
| consensus as-implemented | 1825.2 |
| **consensus, roster-aware** | **2039.2** (+214.0) |
| `alpha_league_aware` (shipped) | 1990.9 |

| Alpha vs roster-aware consensus | |
|---|---|
| mean delta | **−48.3** |
| win rate | **25/50 (50%)** |
| 95% CI | **[−122.2, +25.6]** — contains zero |
| per season | 2021 −25.9 · 2022 +69.5 · 2023 −145.3 · 2024 −155.7 · 2025 +15.9 |

The fair opponent's K+DEF slots score 270.2, essentially identical to Alpha's 275.1 — the
advantage evaporates completely, exactly as the mechanism predicts.

By draft slot, Alpha is behind in 7 of 10 (worst: slot 7 −146.5, slot 1 −135.5, slot 9 −115.7;
best: slot 6 +111.4, slot 4 +77.9).

### 1.4 Why this was not caught earlier

The benchmark's own primary metric is starter points, and starter points are computed on the
best legal lineup — an empty K slot contributes zero silently rather than failing. Nothing in
the harness reports "this roster could not fill 2 of 10 starting slots," and no gate in
`docs/BENCHMARK_SPEC.md` §5 covers the *opponent's* feasibility, only the candidate strategy's.
The `zero_drafted_starting_positions` metric exists in `evaluation/draft_forensics.py` but is
computed only for the tier under test, never for the consensus field.

---

## 2. Why Alpha is behind on the eight skill slots

### 2.1 The mechanism: MSV silently removed positional scarcity

D60 shipped tier M3: `score = (marginal_starter_value + opportunity_cost) × fit × risk ×
survival`, with marginal starter value **replacing** VORP as the value base.

`marginal_starter_value(league, roster, candidate, ...)` is defined as
`best_lineup_points(roster + candidate) − best_lineup_points(roster)`. On an **empty roster**
that is mathematically identical to the candidate's own full projection. So at pick 1, and to
a decreasing degree through the early rounds, the shipped engine's value base is *pure
best-player-available by raw projected points*.

In a 1-QB league raw points favor quarterbacks, and VORP is precisely the correction for that.
Measured top-5 candidates on an empty roster, by each value base:

| season | by MSV (shipped) | by VORP |
|---|---|---|
| 2021 | QB, WR, QB, QB, QB — **4 QBs** | TE, WR, RB, WR, RB — **0 QBs** |
| 2023 | QB, QB, QB, QB, QB — **5 QBs** | WR, WR, TE, WR, WR — **0 QBs** |
| 2025 | QB, QB, QB, QB, WR — **4 QBs** | WR, WR, WR, WR, WR — **0 QBs** |

This is the same pathology that collapses `alpha_bpa` to 463.5 starter points
(`docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §6). In Alpha it is only partially mitigated, by
`roster_fit_multiplier` (bounded [0.7, 1.3]) and the over-cap 0.1× penalty — neither of which
encodes positional replacement level.

### 2.2 The behavioral consequence, measured

Position taken by round, as a percentage of the 50 benchmark drafts:

| round | Alpha QB | Alpha RB | Alpha WR | Alpha TE | cons. QB | cons. RB | cons. WR |
|---|---|---|---|---|---|---|---|
| 1 | 24 | 14 | 50 | 12 | 0 | 44 | 52 |
| 2 | **68** | 4 | 22 | 6 | 2 | 42 | 46 |
| 3 | 8 | 0 | 92 | 0 | 16 | 34 | 46 |
| 4 | 0 | 0 | **100** | 0 | 10 | 30 | 52 |
| 5 | 0 | 22 | 78 | 0 | 16 | 32 | 46 |
| 6–9 | 0 | 30–50 | 0–44 | 2–38 | 12–20 | 24–44 | 28–52 |

| | Alpha | consensus |
|---|---|---|
| mean round of first QB | **1.84** | 14.62 |
| mean round of first RB | **5.24** | 2.72 |
| mean RB count | **2.74** | 5.12 |
| mean WR count | 5.86 | 6.34 |

Alpha takes a quarterback in round 2 in **68% of drafts** in a league that starts one, then
takes wide receivers almost exclusively through round 5, and does not reach running back until
round 5.24 on average. Consensus takes its first RB in round 2.72 and ends with nearly twice
as many.

This is a direct, mechanical consequence of §2.1, and it is the best available explanation for
the −79.6 skill-slot deficit.

### 2.3 Is Alpha's early QB actually wrong?

Not obviously — and this matters, because the directive is explicit that Alpha should be able
to discover the market is wrong. Alpha's projections are not the weak link: `ml_season_catboost`
beats every baseline on MAE at every position (D54), and the raw point gap between an elite QB
and an elite WR is real (2026 board: Josh Allen 382.4 vs the best WR at 290.0).

What Alpha is missing is not the *level* but the *opportunity cost*: taking the QB1 at pick 12
forgoes an RB1 who is worth far more than the QB12 that will still be available in round 10,
because the QB replacement level in a 1-QB league is unusually high. That is exactly what VORP
encodes and what MSV-on-an-empty-roster discards. The claim here is not "QBs are bad early";
it is "the shipped engine no longer has the term that decides whether they are."

---

## 3. K and DEF are drafted far too early

Alpha takes DST in round 10 in **100% of drafts** and K at mean round 10.7 (median 9, earliest
round 6). Both are premium picks in a 16-round draft.

The cost of waiting, measured on realized points:

| position | season | best | 3rd | 6th | 10th | best − 10th |
|---|---|---|---|---|---|---|
| K | 2022 | 160 | 157 | 142 | 138 | **22** |
| K | 2024 | 189 | 173 | 160 | 136 | **53** |
| DST | 2022 | 154 | 133 | 114 | 110 | **44** |
| DST | 2024 | 149 | 126 | 113 | 107 | **42** |

So deferring K/DST from round ~9-10 to rounds 15–16 costs on the order of 20–50 points, and
frees two mid-round picks. Whether that trade is net positive is an empirical question this
phase did not settle — but the current timing was never chosen, it fell out of the formula.

**Mechanism:** with MSV as the value base and the K slot empty, a kicker's value is his *full
projection* (~150), which beats a fourth wide receiver's marginal lineup upgrade (~20). The
`opportunity_cost` term cannot counteract this, because it is VORP-denominated while the value
base is MSV — a scale mismatch introduced by D60 and not noticed at the time.

Note the irony: D60's justification was that MSV *fixed* K/DST hoarding (M0 drafted 3.78 K,
M3 drafts 1.60). That is true and remains a genuine improvement in *count*. It over-corrected
in *timing*.

---

## 4. The ablation that justified D60 was not a controlled comparison

`evaluation/draft_forensics.py::_feasibility_cap` is the **pre-D58 flex-blind, even-bench-split**
formula. `league/roster.py::positional_feasibility_cap` — what production actually calls — is
the D58 flex-aware proportional one. They were never reconciled when D58 changed production.

Measured for `target_league.yaml`:

| position | forensic harness cap | production cap |
|---|---|---|
| QB | 2 | 2 |
| **RB** | **3** | **6** |
| **WR** | **3** | **6** |
| **TE** | **2** | **4** |
| K | 2 | 2 |
| DST | 2 | 2 |

Consequences:

1. Tier **M0**, documented as "the shipped production formula, unchanged — the control"
   (`evaluation/draft_forensics.py`, D58/D60), **is not the shipped production formula.** It
   penalizes a 4th RB, 4th WR and 3rd TE at 0.1× where production does not penalize until the
   7th, 7th and 5th.
2. M3's measured WR count of 5.54 *exceeds* the harness's WR cap of 3, meaning the winning tier
   was absorbing repeated 0.1× penalties that production never applies. The shipped engine's
   behavior was therefore never measured by the ablation that selected it.
3. This explains a discrepancy the documents leave unreconciled: harness M0 = 1894.2 and
   M3 = 2003.8, versus official benchmark 1927.8 (D59) and 1990.9 (D60), for what are supposed
   to be the same two formulas. In the superflex era P3's harness number reproduced the
   benchmark to the decimal; after D58 they diverged and nobody checked.

The *relative* M0-vs-M3 comparison remains internally valid — all four tiers shared the same
(wrong) cap and differed only in the value base — so "MSV beats VORP under a tight cap regime"
is still a real measurement. What is not established is that it holds under production's caps,
and §1–§3 give direct reason to doubt it does.

---

## 5. The pick-level attribution measured the wrong engine

`evaluation/pick_attribution.py` calls `recommend_draft_pick` **without** `roster_player_ids`,
which is the exact argument that switches the value base from VORP to MSV. `draft_simulation.py`
(the official benchmark) and forensic tier H both pass it.

So the 800-pick attribution written up in `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §7 — 738
disagreements, mean delta +23.5, and the RB projection-residual finding — describes the **D55
VORP engine**, not the shipped D60 MSV engine. It is a one-argument fix.

The RB-residual finding itself (consensus RB alternatives in the "cost" bucket overperformed
their own projections by a mean +45.2, n=206) is a statement about *projection error* and is
probably not sensitive to which engine picked the comparison set — but that is an assumption,
not a measurement, and §7's causal attribution to the shipped engine does not hold as written.

---

## 6. Three of four production entry points run an un-benchmarked engine

| call site | `roster_player_ids` | `current_pick_overall` | effective formula |
|---|---|---|---|
| `evaluation/draft_simulation.py` | yes | yes | **MSV + opp-cost (benchmarked)** |
| `cli.py` (`alpha-squad league draft`) | no | sometimes `None` | VORP, opp-cost often zero |
| `agents/registry.py` | no | no | VORP, opp-cost **always zero** |
| `api/routers/league.py` | optional field | yes | MSV only if the client sends it |
| `web/src/components/DraftView.tsx` | deliberately omitted | yes | VORP |

The web omission is correct and documented: `draftedIds` tracks every player drafted
league-wide, not this team's own picks, so passing it would tell the engine the roster already
holds every position anyone has taken. But the consequence is that **the only configuration
that has ever been benchmarked is the one no interactive user reaches.**

---

## 7. What Alpha genuinely does well

Stated with the same evidence standard as the criticisms.

**Consistency.** Across the 50 drafts, Alpha's starter points have stdev **158.9** versus
consensus's **214.5**; Alpha's worst draft is **1570.3** versus consensus's **1392.7**. Alpha's
floor is higher and its spread is tighter. Against the *fair* opponent Alpha still holds a
meaningfully higher floor. For a user who drafts once a season from one slot, variance
reduction is worth real utility, and this is a genuine, reproducible advantage.

**Roster feasibility.** Alpha fills all ten starting slots essentially always; the naive
baselines do not, and neither does the consensus bot. `n_infeasible_rosters` was 0 across all
200 M-tier drafts.

**The K/DST count fix is real.** M0 drafted 3.78 kickers and 2.26 defenses per draft and
breached the K cap in 50/50 drafts; M3 drafts 1.60/1.26 and breaches 0/50. That was a genuine
defect and MSV genuinely fixed it. The over-correction is in timing (§3), not in count.

**The upstream data and market work is sound.** D56's market-series correction, D57's computed
K/DST scoring, and D58's flex-aware capacity were each independently verified in this phase and
none of the findings above impugn them.

---

## 8. Classification of the remaining gap

Against the directive's taxonomy, using the evidence above.

| candidate cause | verdict | evidence |
|---|---|---|
| **Benchmark/data artifact** | **CONFIRMED — dominant** | §1: opponent forfeits 2 of 10 starting slots; worth +245.3 of a +165.7 margin |
| **Positional valuation** | **CONFIRMED** | §2: MSV-as-value-base discards replacement level; 4–5 of top-5 become QBs; 68% round-2 QB |
| **Positional timing** | **CONFIRMED** | §3: DST round 10 in 100% of drafts, K median round 9, against a 20–50 pt cost of waiting |
| **Evaluation methodology** | **CONFIRMED** | §4: the selecting ablation used a different feasibility cap than production; §5: attribution measured a different engine |
| **Opportunity cost / lookahead** | **SUSPECTED, not isolated** | The term is VORP-denominated against an MSV base (§3). Never re-ablated under 1-QB (open since D60). |
| **Projection error** | **PARTIALLY SUPPORTED, unresolved** | RB residual +45.2 (n=206) is real but was measured on the wrong engine (§5); direction plausible, attribution not established |
| **Roster construction** | **NOT SUPPORTED** | Feasibility is 0 failures; the problem is *which* players and *when*, not legality |
| **Information advantage in historical consensus** | **NOT SUPPORTED as an excuse** | Consensus is a preseason ECR snapshot with no more hindsight than Alpha's projections; both are strictly pre-season |
| **Unavoidable variance** | **PARTIALLY** | Fair-opponent CI [−122.2, +25.6] contains zero; some of the 50/50 split is genuinely noise. But the point estimate is negative and the mechanisms above are not noise. |

**Are the losses fixable?** Mixed, and worth separating:

- The K/DEF benchmark artifact is not a loss to fix — it is a *measurement* to fix. Doing so
  removes a phantom win, not a real one.
- The early-QB / late-RB pattern (§2) and the early-K/DST pattern (§3) are concrete,
  mechanism-level, and fixable — both trace to a single design decision (MSV replacing rather
  than complementing VORP).
- Some residual is genuine variance. With 5 seasons × 10 correlated slots the honest unit is
  the season (n=5); a ±50-point mean difference is not distinguishable from noise at that
  sample size, and no amount of engine work will make it so.

---

## 9. Documentation errors found

1. **`docs/DECISIONS.md` D60 and `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §8** report
   `alpha_league_aware` mean total roster points as **2775.9**. The real value in
   `reports/draft_simulation.md` (both runs, determinism-verified) is **2455.0**. The starter
   figure (1990.9) is correct. Corrected in this phase.
   The real 2785.4 → 2455.0 drop in total roster points from D59 to D60 is itself a finding:
   MSV concentrates value into starters and gives up bench depth, which has robustness
   implications the current metric does not capture (see `docs/DRAFT_OBJECTIVE_MODES.md`).
2. **`docs/PROJECT_STATE.md`** status header and milestone table stop at M15 despite M16–M19
   sections existing further down.
3. **M19 summary** says M3 gained "+109.6" starter points; D60 and the diagnostic say +109.7.
4. **`league/draft.py::next_pick_survival_probability`** filters `market_snapshot` on
   `ecr_type` but not `page_type`/`source`, while every other market consumer goes through the
   page_type-scoped `_preseason_overall_market`. D56 exists precisely because `ecr_type='ro'`
   alone mixes `redraft-overall` with a separately-ranked `redraft-idp` board. Latent, not yet
   shown to have changed a result.

---

## 10. Answers to the strategic question

**A. What Alpha does well today.** Fills a legal 10-slot lineup essentially always; produces
markedly more consistent results than consensus (stdev 158.9 vs 214.5, higher floor); its
projection layer beats every baseline on MAE at every position; the market-series, K/DST and
capacity foundations are correct and verified.

**B. What it still does poorly.** Reaches for a QB in round 2 in 68% of drafts in a 1-QB
league; delays its first RB to round 5.24 and ends with 2.74 RBs against consensus's 5.12;
spends round-9/10 capital on K and DST; and is 79.6 points behind consensus on the eight skill
slots that decide the competitive game.

**C. Why it loses to consensus.** Against the *published* opponent it does not lose — but that
opponent forfeits two starting slots, which is worth more than the entire margin. Against a
fair opponent it loses by 48.3 points, and the mechanism is that D60 replaced VORP with
marginal starter value, discarding league-wide positional scarcity from the value base while
gaining lineup-saturation awareness.

**D. What should be changed.** See `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`. In short: fix the
benchmark opponent, fix the two measurement bugs (§4, §5), then test value-base formulations
that retain *both* scarcity and saturation rather than trading one for the other.

**E. What should NOT be changed.** The D56–D58 foundations; the projection models; the
evaluation hierarchy and pre-registration discipline; and — emphatically — nothing should be
tuned against the current benchmark until the opponent is fixed, because that benchmark
rewards exactly the wrong thing.
