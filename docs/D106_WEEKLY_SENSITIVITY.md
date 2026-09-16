# D106 — Does the D105 plateau survive the weekly no-foresight objective?

*(Results in §4 onward; §1–§3 were written before the weekly ladder produced a number.)*

---

## 1. The pre-registered question and decision rule

> **Does the threshold/plateau relationship observed in D105 persist when realized pick value is
> scored with the weekly no-foresight lineup objective?**

    H0  the plateau is OBJECTIVE-SPECIFIC — weekly scoring produces materially more separation
        in realized value as ranking quality degrades.
    H1  the plateau PERSISTS — large changes in ranking and in picks produce little change in
        realized value until ranking quality is substantially degraded.

**The decision rule, fixed before measuring**, using D105's own empirical scale rather than an
invented threshold:

| outcome | criterion |
|---|---|
| **H1 — plateau persists** | at α = 0.50 the weekly value delta stays **below the D97 detection floor (172–250)** *and* **below that level's own seed-to-seed SD**; and the *plateau ratio* stays of the same order as D105's |
| **H0 — plateau resolved** | at α = 0.50 the weekly delta clears **both** the seed SD **and** the detection floor |
| **weakened (intermediate)** | the plateau ratio rises materially but α = 0.50 still sits inside the noise band — detectable in shape, not practically meaningful |

**Plateau ratio** = |Δvalue at α = 0.50| / |Δvalue at α = 1.00|. It is scale-free, which matters
because weekly and season-long totals are not the same units. D105's values:

| format | Δ at α=0.50 | Δ at α=1.00 | **plateau ratio** | seed SD at α=0.50 |
|---|---|---|---|---|
| target_league | −46.5 | −565.8 | **8.2%** | 160 |
| dynasty_1qb | −60.0 | −631.9 | **9.5%** | 127 |

**"Statistically detectable" is not "practically meaningful."** The floor (172–250 points) is the
smallest *draft-level* effect this instrument can resolve at five season clusters; an effect below
it is not actionable regardless of where its interval sits.

## 2. Challenging the premise first

**The brief is right to warn against assuming the weekly objective is better, and the existing
evidence actively predicts H1.** D103 measured that switching from season-long to weekly *reduces*
regret at **every** draft phase (−27.4 target, −38.7 dynasty; late −30.6, −36.8), because a weekly
lineup **adapts** — swapping one player changes the summed weekly total less than it changes a
single season-long allocation. D102's original theory that weekly scoring would expose hidden
late-pick value was refuted by that same measurement.

So the prior from this project's own instruments is that weekly scoring **compresses** differences
between rosters. If that holds, weekly should show **less** separation along the ladder, not more —
which would strengthen rather than resolve the plateau. **A finding of H0 would therefore be
genuinely surprising, and that is what makes the test worth running.**

The north-star is unchanged: pick quality and realized value. The weekly objective is a
*measurement choice* under test here, not a better yardstick by assumption.

## 3. What is held identical to D105, and the one thing that changes

Everything in the D105 ladder is reused **unmodified** — same runner, same functions, same
constants:

- Y1 production decision rule (tier `L0`, pinned to production by D103's
  `TestShippedTierIsProduction`);
- seasons 2021–2025 (`BACKTEST_SEASONS`; **no 2020, no 2026**);
- slots {1, 4, 7, 10}, both shipped 1-QB formats;
- the α ladder **0.00 / 0.25 / 0.50 / 0.75 / 1.00** with D105's exact interpolation
  `key = (1−α)·rank_Y1 + α·rank_random`;
- pre-registered seeds **(0, 1, 2, 3, 4)**, string-seeded, identical at every level;
- the same candidate pools, the same value-multiset preservation, the same information boundary.

**The only intended change is the realized-value objective**, from season-long to
`weekly_lineup_points_no_foresight` — used exactly as D103 established, with no modification to its
implementation.

### Two harness properties that make this a clean isolation

**(a) The weekly lineup is set from UNPERTURBED Y1 projections for every arm.** `_play_draft`
scores with `scoring_static`, and the ladder passes the perturbed board as the *draft* board while
the untouched `static` goes in as the *scorer*. So each arm drafts differently but sets its weekly
lineup the same way. Without this, a scrambled arm would also set worse lineups and the experiment
would confound **draft** quality with **lineup** quality. Pinned by test.

**(b) Pick divergence is objective-independent, so it is NOT re-run.** Picks come from
`_pick_by_tier`, which takes no objective parameter at all — the scoring objective cannot reach a
draft decision. D105's picks-changed table (66.2% / 88.4% / 90.6% / 98.4%) therefore carries over
to D106 **exactly and by construction**, not by re-measurement. Pinned by test.

### One harness hardening, made before the run

`--objective` was an unconstrained string, and `_play_draft` silently falls through to the
season-long branch for any objective it does not recognise — so a typo would have produced a
season-long run reported as a weekly one. The flag now uses `choices=OBJECTIVES` and argparse
refuses. This is the only change D106 makes to any file, and it is in the research layer.

## 4. Results — the weekly ladder

*(Filled in on completion.)*

## 5. D105 versus D106 — the direct comparison

*(Filled in on completion.)*

## 6. Where any change is concentrated

*(Filled in on completion.)*

## 7. Verdict and direction

*(Filled in on completion.)*

## 8. Reproduction

```
uv run python scripts/research/d105_objective_sensitivity.py --mode value \
    --objective weekly_no_foresight --out <dir>      # D106
uv run python scripts/research/d105_objective_sensitivity.py --mode value --out <dir>   # D105
uv run pytest tests/unit/test_d105_objective_sensitivity.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```
