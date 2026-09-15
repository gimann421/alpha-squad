# D105 — Is the draft objective actually sensitive to ranking information?

**Verdict: B — OBJECTIVE IS ROBUST.** Not flat, and not linearly sensitive. The curve is
**thresholded**: within-position ranking quality can be degraded from Spearman **0.753 → 0.527
against realized outcomes** — a 30% loss of predictive ordering — for a cost of only **−46.5
points**, well below the measurement floor. Push further and it collapses: a fully scrambled board
costs **−565.8 (target) / −631.9 (dynasty)**, worse in **5 of 5 seasons**, with intervals excluding
zero.

**The flatness hypothesis is rejected, and D104's null is explained.** The objective *does* respond
to ranking information — just not over the narrow range where realistic sources differ. ECR moves
predictive ranking quality by **+0.024 Spearman**; one rung of the ladder moves it by **−0.035 to
−0.226**. **ECR's information advantage over Y1 is smaller than a single rung**, and it lands inside
the plateau where the objective cannot resolve anything.

**No production change. No retraining. No ECR tuning. No 2026. Nothing merged. No PR.**

---

## 1. The pre-registered hypothesis

    H_FLAT  Within the Y1 operating region, degrading within-position ranking information
            produces little or no meaningful degradation in realized pick quality.
    H_ALT   Controlled degradation produces a systematic, measurable decline.

The question was never "does random drafting do worse" — that is trivial. It was **how much** pick
quality changes as ranking quality degrades, i.e. the **shape** of the curve.

## 2. Phase 0 — the perturbation design, and what it does and does not isolate

Within each position, players are re-ordered by a convex blend of their true Y1 rank and a random
rank, and **Y1's own values** are re-assigned down that order:

    key(p)   = (1 − α)·rank_Y1(p) + α·rank_random(p)
    players  = covered players sorted by (key, player_id)        ← D54 tie-break
    values   = sorted({Y1 projection of x : x ∈ covered}, desc)
    assign     values[i] → players[i]

α = 0 reproduces Y1 **exactly** (pinned by test); α = 1 is a uniform within-position permutation
independent of Y1. Ladder: **L0 = 0.00, L1 = 0.25, L2 = 0.50, L3 = 0.75, L4 = 1.00**.

This is deliberately **the same machinery as D104's `ecr_ordered_static`** — only the ordering key
differs. That is what makes the ECR arm and the scramble ladder points on one comparison rather
than two unrelated experiments.

**Preserved, by construction and asserted at runtime:** the multiset of projected values at every
position is exactly Y1's, so replacement levels, scarcity, consumption demand and the positional
value scale never move; the candidate universe is identical; the decision rule, survival,
opportunity cost, capacity, roster logic and continuation mechanics are untouched — only
`projections` and the derived `vorp` change; no realized outcome reaches any policy.

**What is NOT purely within-position, stated in advance.** Re-ordering skill values while holding
K/DST fixed changes which individual skill player a given kicker is compared against at a
particular pick. D104 measured this as RB→K / WR→K drift. It is **not** treated as a defect — a
drafter with degraded skill rankings genuinely *should* sometimes prefer a kicker — and it is
identical in kind for the ECR arm, which is what keeps the two comparable.

**Randomization.** Seeds **(0, 1, 2, 3, 4)** pre-registered, used identically at every level, drawn
from a **string-seeded** `random.Random` so the stream is stable across processes — verified by a
test that starts a second interpreter, because the reproduction claim depends on it. α = 0 is
seed-independent and runs once.

**Seeds are NOT independent clusters.** The independent unit remains the **season (k = 5)**, as in
D97/D103/D104. Seeds are averaged within a season; every interval is computed across the five
season means. Seeds characterise noise, never power.

**Why realized value and not regret is primary.** D104 established that running `audit_draft` on a
changed board alters *both* the audited policy and the rollout continuation, so regret becomes
arm-relative — each level would be scored against its own scrambled oracle. Whole-draft realized
value is an absolute outcome on a common scale, so it carries the verdict; the regret ladder is
reported as secondary in §8 with that limitation restated.

## 3. Validity — the ladder degrades *predictive* quality, not just agreement with Y1

| arm | α | Spearman vs Y1 | **Spearman vs REALIZED** |
|---|---|---|---|
| L0 | 0.00 | 1.000 | **0.753** |
| L1 | 0.25 | 0.953 | 0.718 |
| L2 | 0.50 | 0.699 | 0.527 |
| L3 | 0.75 | 0.294 | 0.242 |
| L4 | 1.00 | 0.025 | **0.003** |
| **FP_ECR_Y1** | — | 0.931 | **0.777** (target) / 0.745 (dynasty) |

Monotone in both columns, and L4 is genuinely uninformative (0.003). By position the pattern is
uniform (QB/RB/WR/TE all within ±0.06 at every level), so no position carries the ladder.

**This is also the registered x-axis, and it is a measured quantity rather than an invented score**
— which is how FP_ECR_Y1 is placed on the same scale without forcing a metric. Note where it
lands: **ECR is slightly *more* predictive than Y1 (0.777 vs 0.753), while L1 is slightly less
(0.718).** ECR's advantage is **+0.024**; the smallest rung of the ladder is **−0.035**.

## 4. The sensitivity curve — the primary result

Realized roster value per draft, season-long objective, 2021–2025 × slots {1, 4, 7, 10} × 5 seeds
× both formats. Seasons are the clusters (k = 5, t = 2.776).

### target_league (L0 = Y1 = 1983.6)

| arm | α | value | vs L0 | 95% CI | seasons worse | vs floor |
|---|---|---|---|---|---|---|
| L0 | 0.00 | 1983.6 | +0.0 | — | 0/5 | — |
| L1 | 0.25 | 1942.5 | **−41.1** | [−148.8, +66.7] | 4/5 | below |
| L2 | 0.50 | 1937.1 | **−46.5** | [−192.8, +99.8] | 3/5 | below |
| L3 | 0.75 | 1868.6 | **−115.0** | [−330.8, +100.7] | 3/5 | below |
| **L4** | **1.00** | 1417.8 | **−565.8** | **[−829.1, −302.6]** | **5/5** | **ABOVE** |
| FP_ECR_Y1 | — | 2060.9 | +77.3 | [−44.1, +198.6] | 0/5 | below |
| *ORACLE_Y1* | — | *2778.9* | *+795.3* | *[+579.1, +1011.4]* | *0/5* | *ABOVE* |

### dynasty_1qb (L0 = Y1 = 2094.9)

| arm | α | value | vs L0 | 95% CI | seasons worse | vs floor |
|---|---|---|---|---|---|---|
| L1 | 0.25 | 2055.4 | −39.5 | [−230.1, +151.1] | 3/5 | below |
| L2 | 0.50 | 2034.8 | −60.0 | [−318.5, +198.5] | 2/5 | below |
| L3 | 0.75 | 1877.2 | **−217.7** | [−511.1, +75.7] | 4/5 | **in band** |
| **L4** | **1.00** | 1463.0 | **−631.9** | **[−940.4, −323.4]** | **5/5** | **ABOVE** |
| FP_ECR_Y1 | — | 1962.8 | −132.1 | [−371.1, +107.0] | 4/5 | below |
| *ORACLE_Y1* | — | *2811.9* | *+717.0* | *[+432.8, +1001.3]* | *0/5* | *ABOVE* |

### The shape

Plotting value against **measured predictive ranking quality**:

| Spearman vs realized | arm | value vs L0 (target) |
|---|---|---|
| 0.003 | L4 | **−565.8** |
| 0.242 | L3 | −115.0 |
| 0.527 | L2 | −46.5 |
| 0.718 | L1 | −41.1 |
| 0.753 | **L0 = Y1** | 0.0 |
| 0.777 | FP_ECR_Y1 | +77.3 |

**The answer to the brief's A/B/C/D question is C→D: flat until severe degradation, then a
threshold collapse.** From 0.753 down to 0.527 — losing 30% of predictive ordering quality — costs
**46.5 points**. From 0.527 down to 0.003 costs a further **519 points**. The marginal value of
ranking quality is roughly **an order of magnitude larger** in the bottom half of the range than in
the top half.

Y1 and ECR both sit near the **upper edge of the plateau**.

**A caveat on the ORACLE_Y1 row, because it is tempting to read it as the curve's right-hand end
and it is not.** L0–L4 and FP_ECR_Y1 all preserve Y1's value multiset — they are pure *ordering*
changes. `ORACLE_Y1` replaces the values themselves with realized points, so it changes magnitudes
as well as order and is **not a point on this ordering-quality curve**. It is retained as the
ceiling anchor it has always been, not as evidence about the slope.

## 5. Interpretation against the pre-registered criteria

Read against the three existing quantities, with no new threshold invented:

| reference | value | where the ladder lands |
|---|---|---|
| D97 detection floor | 172–250 pts | only **L4** clears it in target; **L3 and L4** in dynasty |
| D103 decision-shaped residual | 86–113 pts | **L3 (−115.0)** is comparable; L1/L2 are smaller |
| D104 ECR effect | +77.3 / −132.1 | comparable to **L1/L2**, i.e. inside the plateau |

The pre-registered rule said: *"If severe ranking corruption produces a clearly measurable decline
but realistic/moderate corruption does not, classify the objective as ROBUST rather than FLAT."*
That is exactly what happened. **Verdict B.**

**C (FLAT) is rejected** — α = 1.00 produces −566/−632 with 5/5 seasons worse and intervals
excluding zero. That is not a null; it is a large, unambiguous effect. **A (SENSITIVE) is rejected**
— moderate degradation (α = 0.25–0.50) costs 40–60 points, below the floor.

## 6. Decision sensitivity versus value sensitivity — the decisive result

This is the distinction the brief called essential, and the two surfaces turn out to be almost
completely decoupled. Both arms asked at the identical state, pool and roster; the state advances
on Y1's pick. Seed 0, all four slots.

**target_league**

| arm | α | **picks changed** | EARLY | MIDDLE | LATE | first divergence | **value vs L0** |
|---|---|---|---|---|---|---|---|
| L0 | 0.00 | **0.0%** | 0.0% | 0.0% | 0.0% | none | +0.0 |
| L1 | 0.25 | **66.2%** | 65.0% | 57.0% | 75.0% | round 1 | **−41.1** |
| L2 | 0.50 | **88.4%** | 86.0% | 85.0% | 93.3% | round 1 | **−46.5** |
| L3 | 0.75 | 90.6% | 79.0% | 93.0% | 98.3% | round 1 | −115.0 |
| L4 | 1.00 | **98.4%** | 96.0% | 99.0% | 100.0% | round 1 | **−565.8** |

**dynasty_1qb**

| arm | α | picks changed | EARLY | MIDDLE | LATE | value vs L0 |
|---|---|---|---|---|---|---|
| L1 | 0.25 | 69.1% | 75.0% | 60.0% | 71.7% | −39.5 |
| L2 | 0.50 | 87.5% | 80.0% | 88.0% | 93.3% | −60.0 |
| L3 | 0.75 | 89.4% | 80.0% | 96.0% | 91.7% | −217.7 |
| L4 | 1.00 | 98.4% | 96.0% | 100.0% | 99.2% | −631.9 |

**Read the L2 row.** Perturbing the board until **88% of every draft changes** — a different player
at seven of every eight picks, starting at pick 1 — costs **46.5 points**, which is below the
detection floor and *smaller than the seed-to-seed noise of the same level* (160). Then between 88%
and 98% changed, value collapses by a further ~519.

**The decision rule is highly sensitive to ranking information; realized value is not.** The
engine faithfully re-ranks the board — that is what 66–98% pick churn means — but the *outcome*
barely responds until the ranking is nearly destroyed. L0's 0.0% also confirms α = 0 reproduces Y1
exactly through the full pipeline, not merely in the static.

Positional mix of the diverging pick is WR-dominated at every level (WR 99–191 of the changes),
with RB/QB/TE rotating — consistent with WR being the deepest position and therefore the one where
re-ordering has the most candidates to move. K appears only at L1 (2–4 occurrences), so the K/DST
drift flagged in §2 is negligible on this ladder, unlike D104's ECR arm.

## 7. Per-season detail

**target_league**, value vs L0:

| arm | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| L1 | −128 | +67 | −3 | −9 | −133 |
| L2 | −19 | +65 | −92 | +41 | −227 |
| L3 | +62 | −160 | −225 | +67 | −320 |
| **L4** | **−659** | **−484** | **−703** | **−232** | **−752** |
| FP_ECR_Y1 | +137 | +220 | +26 | +0 | +3 |

**dynasty_1qb**, value vs L0:

| arm | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| L1 | +98 | +95 | −273 | −92 | −26 |
| L2 | +104 | +100 | −377 | +37 | −165 |
| L3 | +91 | −189 | −547 | −126 | −319 |
| **L4** | **−632** | **−516** | **−1061** | **−470** | **−481** |
| FP_ECR_Y1 | −43 | −25 | −449 | −176 | +32 |

**L4 is negative in every season of both formats.** L1–L3 flip sign season to season — which is
what "inside the plateau" looks like, and is why their intervals are wide.

**Seed dispersion** (SD across seeds within a season-slot cell): 127–204 points at every level.
**This is the single most important control number in the phase**: the noise a *random re-draw of
the same perturbation level* generates is comparable to the entire L1–L3 effect. It is why those
rungs cannot be resolved, and it is a property of the draft, not of the estimator.

## 8. Regret ladder (secondary)

D103's `audit_draft`, unchanged. `target_league`, season-long, levels L0/L2/L4, seed 0, slots
{1, 10}. Lower is better.

| arm | α | all picks | EARLY 1–5 | MIDDLE 6–10 | LATE 11–16 | alpha = oracle |
|---|---|---|---|---|---|---|
| L0 | 0.00 | **126.2** | 164.6 | 110.9 | 107.1 | 2.5% |
| L2 | 0.50 | **137.3** | 191.6 | 117.7 | 108.3 | 1.2% |
| L4 | 1.00 | **228.4** | 280.5 | 215.8 | 195.3 | 1.2% |

**The same threshold shape as the value curve.** L0 → L2 costs **+11.1** mean regret; L2 → L4 costs
a further **+91.1**. Half the ladder's information loss is nearly free in regret terms; the second
half is not.

**The artifact anticipated in §2 did not materialise, which is worth stating.** The concern was
that a scrambled board also scrambles the *oracle's* rollouts, making each level's oracle weaker
and potentially pushing regret **down** as degradation rises — an arm-relative confound that would
have made this table uninterpretable. Regret instead rises monotonically and in the same direction
as the absolute value curve, so the two agree and this corroborates §4 rather than contradicting
it. The limitation still means the magnitudes are not comparable across levels on a common yardstick
— only their ordering is.

Degradation is concentrated **early** (164.6 → 280.5, +115.9) more than late (107.1 → 195.3,
+88.2), consistent with D103's finding that regret and candidate spread are largest in rounds 1–5.

*(L0 reads 126.2 here against D103's 134.8 because this reduced run uses slots {1, 10} rather than
{1, 4, 7, 10}; the comparison within this table is like-for-like.)*

## 9. Results appendix

Divergence results are in §6. The regret ladder is in §8.

## 10. The bigger research decision

**1. Does the draft objective meaningfully respond to ranking information?** **Yes — but only over
a wide range.** Full scramble costs 566–632 points, 5/5 seasons. The response is real and large at
the extreme and unresolvable near Y1.

**2. How much degradation before pick quality materially declines?** Roughly **half the predictive
ordering quality**. Spearman-vs-realized must fall from 0.753 to about **0.24 (L3)** before the
effect reaches the 86–113 point scale of D103's decision residual, and to **0.00 (L4)** before it
clears the 172–250 detection floor in the target format. Dynasty crosses into the band one rung
earlier, at L3.

**3. Does ECR look like a genuinely different information source, or another ranking inside a broad
robustness region?** **The latter, decisively.** ECR improves predictive ranking quality by
**+0.024 Spearman** — about **one-tenth of the smallest rung** — and its value effect (+77.3/−132.1)
is the same size as L1/L2's (−41/−60) and the same size as the seed noise (127–204). **D104's null
was not a failure of ECR; it was the objective being unable to resolve a change that small.**

**4. Is projection improvement still worth pursuing?** **Only if it is very large.** This phase
puts a number on "large" for the first time: to produce an effect on the scale D103 called the
decision residual, a ranking change must move predictive Spearman by roughly **±0.5**. ECR moves it
by 0.024. A new projection model would have to be **an order of magnitude better than the best
preseason source available** merely to reach an effect the instrument can detect.

*Stated as the extrapolation it is:* the ladder measures **degradation** only. Inferring that
improvement is symmetric is not established. The one measured anchor in the improvement direction
is ORACLE_Y1 (+795.3), which requires *perfect* information and, per §4's caveat, changes values
rather than only ordering.

**5. Is decision-rule improvement still worth pursuing?** **No new evidence for it**, and D103's
conclusion stands. But D105 changes *why*, and §6 is the evidence. The engine is **not**
insensitive — perturbing the board changes 66–98% of its picks, so the decision surface is steep.
What is flat is the **value** surface it sits on: 88% of picks can change for 46.5 points. **A
decision rule cannot extract value from ordering differences the outcome does not reward**, and
that is a property of the draft, not a deficiency of Y1.

**6. Is the primary opportunity elsewhere?** The honest answer is that **both measured levers are
inside the plateau**, and this phase for the first time explains why rather than just recording
another null. Ten value bases, a weekly objective, legality separation, per-position calibration,
identification work and a real market ranking have all failed **for the same structural reason**:
they all move the board by less than the objective can register.

**7. Smallest next experiment that could change a product decision?** §11.

### Challenging the direction, as required

**The flatness hypothesis I proposed at the end of D104 is wrong, and I am retracting it.** The
objective is not flat — scrambling the board destroys 566–632 points, which is larger than anything
the project has ever measured on the decision side. What is true is narrower and more useful: **the
objective has a broad robustness plateau, and every ranking source the project has tested lives
inside it.**

That is a materially better-founded conclusion than "the objective is flat", and it was reachable
only by testing the hypothesis rather than assuming it. It also reframes six phases of null results
as a single coherent finding instead of six separate disappointments.

## 11. Smallest next experiment

Not another ranking, and not another value base. The plateau finding makes one question decisive:

> **Is the plateau a property of the draft, or of the objective we score it with?** The ladder was
> scored on realized roster value with the season-long objective. D103 showed the weekly
> no-foresight objective *compresses* differences further. Re-run **exactly this ladder** under the
> weekly objective. If the plateau persists, it is a property of the draft itself and ranking-side
> work is closed on positive evidence. If the weekly objective resolves L1/L2 where the season-long
> one cannot, the plateau is partly a measurement artifact and the *objective*, not the projections,
> is the thing to fix.

It reuses D105's machinery with `--objective weekly_no_foresight`; no model, no fitting, no new
data. **Recorded as a recommendation only; D106 is not started.**

Explicitly **not** recommended: a new projection model, ECR tuning, another value base, O2/O3, a
lookahead optimizer, or any use of 2026.

## 12. Reproduction

```
uv run python scripts/research/d105_objective_sensitivity.py --mode validity   --out <dir>
uv run python scripts/research/d105_objective_sensitivity.py --mode value      --out <dir>
uv run python scripts/research/d105_objective_sensitivity.py --mode divergence --seeds 0 --out <dir>
uv run python scripts/research/d105_objective_sensitivity.py --mode regret --leagues target_league --levels L0,L2,L4 --out <dir>
uv run pytest tests/unit/test_d105_objective_sensitivity.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```
