# D104 — How much of the measured oracle gap does a real preseason ranking recover?

> **§9's closing hypothesis is SUPERSEDED BY D105** (`docs/D105_OBJECTIVE_SENSITIVITY.md`), which
> tested it directly. D104 proposed that "the draft objective is FLAT near Y1's operating point".
> **It is not flat — it is thresholded.** A fully scrambled within-position board costs −565.8
> (target) / −631.9 (dynasty), worse in 5 of 5 seasons. The correct statement is narrower: the
> objective has a broad **robustness plateau**, and every ranking source tested — Y1 and ECR alike —
> lives inside it. D105 also explains D104's null: ECR improves predictive ranking quality by
> +0.024 Spearman, about one-tenth of the smallest rung of D105's ladder.
>
> Everything else in this report — the Phase 0 rejection of `ecr_implied_baseline`, the
> decomposition, the 57–64% pick churn, and the "identifies better players ≠ produces better picks"
> conclusion — stands.

**Verdict: B — SMALL / UNCERTAIN ACHIEVABLE HEADROOM.** The strongest legitimate preseason ranking
in this repository, substituted into the Y1 decision rule with the rule held fixed, recovers
**+77.3 points (9.7% of the measured oracle gap) in `target_league`** — directionally consistent
across all five seasons but **below the measurement floor** — and **−132.1 points (−18.4%) in
`dynasty_1qb`**, where it makes drafts *worse* in four of five seasons.

**The headline is a negative result that matters more than the positive one.** D100 established
that FantasyPros ECR identifies realized top-6 players better than M6 (2.75 vs 1.95 of 6). D104
tested whether that translates into better draft picks. **It does not.** Changing **57–64% of all
picks** moves realized roster value by less than 10% of the oracle gap in one format and
*negatively* in the other.

**No production change. No model fitted. No ECR tuning. No 2026. Nothing merged. No PR.**

---

## 1. The exact research question

Holding the **Y1 decision rule fixed**, measure the chain

    Y1  →  FP_ECR_Y1  →  ORACLE_Y1

where `FP_ECR_Y1` carries the strongest legitimate preseason ECR ordering already in the repository
and `ORACLE_Y1` (from D103) carries realized outcomes. `ORACLE_Y1` is the information **ceiling**
and is nowhere described as achievable.

## 2. Phase 0 — challenging the experiment first

The repository's existing ECR→value transformation is
`models/baselines/market_implied.py::ecr_implied_baseline` (walk-forward isotonic rank→points).
**It was inspected and rejected for this job, before any comparison was run, on three independent
measured grounds.**

**(a) It destroys the ordering under test.** The isotonic step function collapses the top of the
board. Measured on 2023, distinct values among the top 24 by value:

| position | distinct values in top 24 | largest tie group |
|---|---|---|
| RB | **4** | **12** |
| WR | 6 | 6 |
| QB | 9 | 8 |
| TE | 12 | 4 |

The draft engine sorts `(-score, player_id)`, so an arm built on this would choose among 4–12 tied
players **alphabetically** — precisely in rounds 1–5, where D103 measured regret to be
concentrated. That measures an isotonic map plus alphabetical tie-breaking, not ECR's information.
This is the same degeneracy class D91 investigated and D95 fixed for the 2020 empty board.

**(b) It is hardcoded to `ecr_type='ro'`** (`market_implied.py:_preseason_ranks_for_season`) and
ignores the league's resolved series. `dynasty_1qb` resolves to `do`/`dynasty-overall`, so the
shipped transformation would feed it the **redraft** board — a direct D56 violation. Half the
registered population could not be measured at all.

**(c) Coverage is 66–75% of the board**, and only QB/RB/WR/TE (`_POSITIONS`); K and DST get no
value. Substituting it changes the candidate universe and breaks the pool parity the comparison
depends on.

### What was used instead, and why it is an information change rather than a valuation change

`ecr_ordered_static` re-assigns, **within each position**, Y1's own projected values to players in
preseason ECR order:

    C       = board players at this position carrying an ECR rank
    values  = sorted({Y1 projection of x : x ∈ C}, descending)
    players = C sorted by (ecr_rank ascending, player_id)      ← D54 tie-break
    assign    values[i] → players[i]
    players not in C keep their Y1 projection, untouched

- The **multiset of projected values at every position is exactly Y1's** — asserted at runtime and
  pinned by test — so replacement levels, scarcity, consumption demand and the positional value
  scale are all unchanged. No new valuation function.
- Only **which player holds which value** changes. That is the ordering information D100 measured.
- The candidate universe is identical, so **pool parity holds by construction**.
- It introduces **no ties** beyond Y1's own.

The board read is `SeasonStatic.market_rank` — loaded by the instrument through the league's
**resolved** series with the correct `page_type`, restricted to **July/August scrapes of the target
season**. It is the same board the opponent model and the survival term already consume.

### Phase 0 answers to the ten questions

| # | question | answer |
|---|---|---|
| 1 | what ECR data is available? | `market_snapshot`: `ro`/`redraft-overall` (142 831 rows), `do`/`dynasty-overall` (155 216), plus `rsf`, `dsf` and IDP pages |
| 2 | which snapshot/page? | the league's **resolved** series; July/August of the target season; latest such scrape per player |
| 3 | genuinely pre-draft? | **yes** — scrapes run 2021-07-02…2025-08-30, all before the September season start |
| 4 | consistent across 2021–2025? | yes, every cell populated in both formats |
| 5 | same player universe as the draft? | **no — 71–86% coverage**, handled by leaving uncovered players at their Y1 value so the universe is unchanged |
| 6 | players in one arm but not another? | **none** — parity is structural and tested |
| 7 | positional or overall ranking? | overall rank, used **within position** |
| 8 | substitutable without a new valuation model? | **yes**, via the value permutation above |
| 9 | repository-defined ECR→value transform? | yes (`ecr_implied_baseline`) — rejected for (a)/(b)/(c) |
| 10 | invented after seeing results? | **no.** The rejection and the replacement were both fixed in the runner's pre-registration before any comparison ran |

### Leakage audit

`page_type` contamination was measured rather than assumed: `market_implied`'s query omits the
`page_type` filter, and `redraft-idp` rows exist in every season (1 469–2 590). Differences against
the page-filtered board: **0/496, 0/500, 0/481, 0/549, and 1/488 (2025)** — one WR in five seasons.
Inert in practice, consistent with D98's finding for the feature path, and recorded as the same
latent fragility D96 §7 flagged. The instrument path used by D104 (`static.market_rank`) applies the
filter correctly and is unaffected.

## 3. Instrument validation — ORACLE_Y1 reproduces D103 exactly

Required before interpreting anything:

| format | D103 recorded | D104 re-run | match |
|---|---|---|---|
| target_league | +795.3 | **+795.3** | exact |
| dynasty_1qb | +717.0 | **+717.0** | exact |

Deterministic reproduction. The instrument is sound and the new arm can be interpreted.

## 4. The decomposition — Y1 → FP_ECR_Y1 → ORACLE_Y1

Realized roster value per draft, season-long objective, 2021–2025 × slots {1, 4, 7, 10} × both
formats (20 drafts per arm per format). Seasons are the independent clusters (k = 5, t = 2.776).

### target_league

| arm | mean realized value |
|---|---|
| Y1 | 1983.6 |
| FP_ECR_Y1 | 2060.9 |
| ORACLE_Y1 | 2778.9 |

| contrast | effect | 95% CI | t | seasons |
|---|---|---|---|---|
| **1. Y1 → FP_ECR_Y1** | **+77.3** | [−44.1, +198.6] | 1.77 | **5W/0T/0L** |
| 2. FP_ECR_Y1 → ORACLE_Y1 | +718.0 | [+504.1, +931.9] | 9.32 | 5W/0T/0L |
| 3. Y1 → ORACLE_Y1 | +795.3 | [+579.1, +1011.4] | 10.21 | 5W/0T/0L |

Per season (Y1 → FP_ECR_Y1): 2021 +137, 2022 +220, 2023 +26, 2024 +0, 2025 +3.

**Fraction of this measured oracle gap recovered by the tested preseason ECR benchmark: +9.7%.**
*(Not a causal estimate and not a generalization beyond this experiment.)*

### dynasty_1qb

| arm | mean realized value |
|---|---|
| Y1 | 2094.9 |
| FP_ECR_Y1 | **1962.8** |
| ORACLE_Y1 | 2811.9 |

| contrast | effect | 95% CI | t | seasons |
|---|---|---|---|---|
| **1. Y1 → FP_ECR_Y1** | **−132.1** | [−371.1, +107.0] | −1.53 | **1W/0T/4L** |
| 2. FP_ECR_Y1 → ORACLE_Y1 | +849.1 | [+714.7, +983.5] | 17.54 | 5W/0T/0L |
| 3. Y1 → ORACLE_Y1 | +717.0 | [+432.8, +1001.3] | 7.00 | 5W/0T/0L |

Per season: 2021 −43, 2022 −25, 2023 −449, 2024 −176, 2025 +32. **Recovered fraction: −18.4%.**

### Against the pre-registered stopping rule

D97's measurement floor for a draft-level contrast is **172–250 points**. Both effects are **below
it**, so both are classified **UNRESOLVED** by the rule fixed in advance — the positive one
included. No downstream production run, 2026 check, retraining or tuning follows.

**The sign flips across formats.** Under the project's own G7-style generalization reasoning
(D89/D90), an effect that reverses on a second shipped format has not demonstrated a mechanism.

## 5. Where ECR changes picks — and why that makes the value result striking

Both arms asked at the identical state, pool and roster; the state advances on Y1's pick.

| format | picks changed | EARLY 1–5 | MIDDLE 6–10 | LATE 11–16 | first divergence |
|---|---|---|---|---|---|
| target_league | **183/320 (57.2%)** | 57.0% | 52.0% | 61.7% | round 1, in 20/20 drafts |
| dynasty_1qb | **206/320 (64.4%)** | 63.0% | 66.0% | 64.2% | round 1, in 20/20 drafts |

> **[Corrected in D107 §2 C2; re-verified independently in D108. The table is left as published;
> this note is authoritative for the last column.]** The measured first-divergence histogram is
> **target {1: 11, 2: 5, 3: 3, 5: 1}** and **dynasty {1: 11, 2: 5, 3: 1, 4: 2, 5: 1}** — so **all
> 20 drafts diverge and all do so within five rounds, but the first divergence is round 1 in 11 of
> 20, not 20 of 20.** Every other figure in this table reproduces exactly. Read "starting at pick
> 1" below as "starting in the opening rounds".

Position swaps (Y1 → ECR), target: WR→WR 44, RB→RB 20, QB→QB 19, **RB→K 17, WR→K 14, TE→K 12**,
TE→TE 10, RB→WR 6. Dynasty: WR→WR 29, RB→WR 20, QB→QB 15, RB→RB 15, **RB→DST 15**, TE→TE 15,
WR→K 14, WR→TE 13.

**This is the phase's most informative number.** Reordering the board changes **more than half of
every draft, starting at pick 1**, and realized value moves by less than 10% of the oracle gap —
negatively in one format. The draft outcome is remarkably **insensitive to within-position ordering
of the board**, which is exactly what D103's "92–96% of divergences are luck-shaped" predicts.

**One honest confound:** although the permutation is within-position, its *effect* is not purely
within-position. Re-assigning skill values changes their standing relative to the **untouched**
K/DST baselines, which is why RB→K, WR→K and RB→DST swaps appear. Those are a side effect of
holding K/DST fixed (the right choice, since no ECR board ranks them), not of ECR's opinion about
kickers. It is a real limitation of the isolation and is reported rather than smoothed over.

## 6. Pick-level regret (secondary — with an interpretive limit)

**An important limitation, stated before the numbers:** running D103's `audit_draft` on the
ECR-informed board changes **both** the audited policy **and** the rollout continuation. Each arm
is therefore scored against **its own** oracle, so regret here is *arm-relative* — a lower number
can mean "better picks" or "a weaker oracle to be measured against". **The whole-draft realized
value in §4 is the cleaner primary**, because it is an absolute outcome on a common scale. This is
why §4, not §6, carries the verdict.

## 7. The three registered questions

**Q1 — Does ECR actually improve pick quality?** **Marginally in one format, not in the other.**
+77.3 (target, 5/5 seasons, below the floor) and −132.1 (dynasty, 1W/4L). Directional consistency
in target is real; magnitude is not resolvable and the sign does not hold across formats.

**Q2 — Where does it help?** The value effect is too small and too noisy to attribute to a phase or
position without promoting an exploratory subgroup, which the brief forbids. What *is* measurable is
where it **changes** picks: everywhere, from round 1, in 57–64% of picks, fairly evenly across
phases. The honest answer is that **the churn is uniform and the benefit is not localizable.**

**Q3 — How much of the information gap remains?** **Nearly all of it.** After substituting the best
available preseason ranking, +718.0 (target) and +849.1 (dynasty) of oracle headroom remains — more
than 90% of the measured gap in target, and *more than 100%* in dynasty because ECR moved backwards.

## 8. The distinction the phase was built to test

> "FantasyPros identifies better players" ≠ "FantasyPros produces better draft picks."

D100 established the former (2.75 vs 1.95 of 6 on top-6 identification, plus AUC and Spearman).
**D104 tested the latter directly and it does not follow.** A ranking that is materially better at
picking out the eventual top 6 produces a draft worth +77.3 points in one format and −132.1 in
another. That is the clearest demonstration this project has that **projection proxy metrics do not
transfer to pick quality**, and it retires the chain of reasoning that ran from D97 through D100.

Likewise: "the oracle is much better" ≠ "we can achieve that improvement." The intermediate arm
existed precisely to separate those, and it shows **the oracle gap is largely not reachable from
preseason ranking information.**

## 9. The bigger decision

**1. Is the Y1 decision rule still the primary bottleneck?** **No — and neither is anything else
that has been measured.** D103 put the decision-shaped residual at ~86–113 points/draft, below the
172–250 floor. D104 now puts the best available preseason-information gain at +77.3/−132.1, also
below the floor. **Neither lever has demonstrated reachable headroom above the measurement floor.**

**2. Is projection/information quality now the more credible opportunity?** **Weaker than D97–D100
implied.** The credible part of the information gap — the part reachable from a real preseason
source — is ≤10% of it in the format where it helps at all. The rest is outcome variance that did
not exist at preseason in any form.

**3. How much of the oracle gap is recoverable with this actual source?** **+9.7% (target),
−18.4% (dynasty).** Both below the floor; the second is negative.

**4. Does this justify building a new projection model?** **No.** The strongest real preseason
ranking available recovers under a tenth of the gap and is harmful in dynasty. A new model would
have to beat ECR by a wide margin merely to reach an effect the instrument still could not detect.

**5. Does it justify changing the decision rule?** **No new evidence for it**, and D103's
conclusion stands. But see the challenge below.

**6. Smallest next experiment that would change one of those decisions?** §10.

### Challenging the direction again, as required

**The evidence now says the problem is NOT projections — at least not in the sense the last six
phases assumed.** D97 read a large oracle gap as projection headroom; D100 found a proxy on which
ECR beats M6; D101 and D102 chased that; D103 showed the decision residual is tiny; **D104 shows the
information gap is mostly not reachable either.** Continuing the projection path because it was the
previous recommendation would be exactly the error the brief warns against.

> **[Too strong. Superseded by D107 §6.1, re-affirmed in D108 §4; this note is authoritative.]**
> D105/D106 went on to measure a **566–721 point** cost to destroying the projection ordering, so
> "the problem is NOT projections" must not be carried forward as stated. The defensible form is:
> *not the projection-quality differences available from the sources tested, at the resolution this
> instrument has.* Three limits belong beside it permanently — the D105/D106 ladder is
> **degradation-only** (there is no improvement-side rung), it holds each position's **value
> multiset fixed** (so it tests within-position *ordering* and says nothing about projection
> *magnitudes* — the axis of D97's +65.2 QB top-6 bias and D99's X2/X3 arms), and it was run
> against **one** real alternative ranking source. The section's own hedge, "at least not in the
> sense the last six phases assumed", is the part that survives.

**Does the decision rule deserve another look despite D103?** On this evidence, **no — but for a
new reason.** §5 is the pivot: changing 57–64% of picks moves realized value by almost nothing.
That is evidence that the draft objective is **flat** near Y1's operating point — many quite
different boards produce roughly the same roster value. A flat objective means *neither* better
ordering *nor* a cleverer rule buys much, and it explains why ten value bases, a weekly objective
and legality separation have all failed. **The plateau is a property of the problem, not a failure
of the search.**

That is a materially different conclusion from "keep improving projections", and it is what the
evidence supports.

## 10. Smallest next experiment

Not another projection source, and not another value base. The one question whose answer would
actually change a decision:

> **Is the draft objective genuinely flat near Y1, or is the instrument insensitive?** Measure the
> dispersion of realized roster value across *deliberately* perturbed boards — e.g. random
> within-position permutations of Y1's values at increasing intensity — with the rule held fixed.
> If heavily scrambled boards land within the same ~±130-point band that ECR does, the objective is
> flat and **no ranking-side work can pay**, which closes the projection direction on positive
> evidence rather than on repeated null results. If value degrades sharply with scramble intensity,
> then Y1's ordering *is* doing real work and ECR simply is not better at it — a different and also
> actionable conclusion.

It reuses the D104 machinery with a different permutation, needs no model, no fitting and no new
data. **Recorded as a recommendation only; D105 is not started.**

Explicitly **not** recommended: a new projection model, ECR weight tuning, another value base,
O2/O3, a lookahead optimizer, or any use of 2026.

## 11. Pick-level regret results

D103's `audit_draft`, unchanged, `target_league`, season-long objective, 2021–2025 × slots
{1, 4, 7, 10} × both arms = 320 audited picks per arm. Lower is better.

| arm | all picks | EARLY 1–5 | MIDDLE 6–10 | LATE 11–16 | alpha = oracle |
|---|---|---|---|---|---|
| Y1 | **134.8** | 181.5 | 121.0 | **107.4** | 2.2% |
| FP_ECR_Y1 | **139.8** | 180.6 | 119.4 | **122.8** | 1.2% |

**FP_ECR_Y1 − Y1 = +5.0 mean regret** (i.e. slightly *worse*), 95% CI [−33.2, +43.3], t = 0.36,
better in only **2 of 5 seasons**. The arm also matches the oracle's pick less often (1.2% vs 2.2%).

Mean regret at picks where each position was taken:

| arm | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| Y1 | 164 | 113 | 157 | **119** | **113** | **117** |
| FP_ECR_Y1 | 166 | 111 | 164 | **140** | **123** | **123** |

**Two readings, both consistent with §4.** First, the pick-level metric shows **no improvement** —
the point estimate is in the wrong direction and the interval spans zero, matching a whole-draft
effect of +77.3 whose interval also spans zero. Second, the damage is concentrated **LATE**
(107.4 → 122.8) and at **TE/K/DST**, which is exactly the cross-position confound flagged in §5:
re-assigning skill values while holding K/DST fixed pulls the engine toward kickers and defenses in
the endgame, and those picks carry higher regret.

Read subject to §6's limitation — each arm is scored against its own oracle — so this corroborates
the §4 verdict rather than independently establishing it.

## 12. Reproduction

```
uv run python scripts/research/d104_ecr_floor.py --mode decomposition --out <dir>
uv run python scripts/research/d104_ecr_floor.py --mode divergence    --out <dir>
uv run python scripts/research/d104_ecr_floor.py --mode regret --leagues target_league --out <dir>
uv run pytest tests/unit/test_d104_ecr_floor.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```
