# D103 — Pick-level regret by draft phase, and the information-vs-decision decomposition

**Verdict: D — NOT CONFIRMED.** The measurement is now established and validated; what is *not*
confirmed is any decision-rule opportunity. Two of D102's claims are **refuted by this phase's own
data and are corrected below**. `models/` and `league/` remain byte-identical to the Y1 baseline;
no production decision logic changed; nothing merged; no PR.

**The three findings that matter:**

1. **Regret is concentrated EARLY, not late** — 181.5 in rounds 1–5 against 107.4 in rounds 11–16
   (target, season-long), monotone across phases in all four league × objective cells.
2. **The weekly objective *reduces* measured regret everywhere** (−27.4 target, −38.7 dynasty),
   including late (−30.6, −36.8). It does not expose hidden late-pick value. **This is the opposite
   of what D102 predicted when it recommended this experiment.**
3. **~93–96% of divergences are luck-shaped.** The structural residual is 0.70–1.20 picks per draft
   worth ~86–113 points per draft — which **independently reproduces D86's ~90** on a different
   slot set, and sits below D97's ~172–250 point measurement floor.

---

## 1. Repository status (Phase 0)

| check | result |
|---|---|
| working tree at start | clean |
| branch / HEAD at start | `d102-pick-level-objective`, `a4d191e` |
| `origin/main` | `277204f` (D97 merged) |
| **D95 merged** | yes — `c5614f8` (PR #20) |
| **D96 merged** | yes — `7d8898c` (PR #21) |
| D93 O-tier dispatch repair | present (`draft_forensics.py:1981`) |
| `BACKTEST_SEASONS` | `(2021, 2022, 2023, 2024, 2025)` |
| `models/` | `73b408e9bd12daecdd6a2a875e48735319b66aef` — **unchanged** |
| `league/` | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — **unchanged** |
| baseline tests / lint | 1370 passed, 44 deselected; ruff clean |
| board vintage | `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99` |

## 2. Challenging the objective before measuring it

The north-star — *maximize the expected value of the roster from each pick forward* — survives
contact with the instruments, with one qualification that shapes everything below.

It survives because the engine already optimizes a state-conditional marginal quantity
(`marginal_starter_value` + draft-aware VORP + positional opportunity cost, times fit, confidence
and survival), and because `draft_oracle.py` already measures the matching counterfactual.

The qualification: **a one-step oracle can only measure the regret of one pick against a fixed
continuation.** It cannot measure "the best decision at every pick" jointly, because that is a
dynamic program over a 160-pick game on a ~610-player board. Every number here is therefore a
*lower bound on the value of a better objective*, and is reported as such rather than as the value
of playing optimally.

## 3. Part 1 — production equivalence is now pinned

`draft_oracle.py` claimed `L0`/`Q0`/`Z0` were "asserted byte-identical to `recommend_draft_pick` by
existing tests". **No such test existed.** `test_l0_is_the_shipped_engine` compares L0 only to its
sibling replicas Q0/Z0 — a drift common to all three passed silently — and the only test touching
production pinned tier `H` on the **first pick** of a synthetic 5-round league.

Added `TestShippedTierIsProduction`: it walks whole drafts at **every** slot and compares the
**chosen player** against tier `H` (a direct pass-through to `recommend_draft_pick`) at every state
the oracle audits, continuing on *production's* pick so a divergence cannot hide by forking the
state. A companion test proves the comparison can fail (tier `A` trips the same assertion).

*Correction made during the phase:* the first version of that guard compared a single pick, and
tier `A` happens to agree with production on the obvious first pick — so the guard passed while
proving nothing. It now runs a whole draft.

**Scope, stated rather than implied:** these run on the offline fixture board, because the suite
never opens the real database. The real-data companion (`--mode parity`) is in the runner; the
same comparison over 2021–2025 × slots {1,5,10} × 16 rounds agreed on **240 of 240** pick states
when D102 ran it.

## 4. Part 2 — the oracle's objective is selectable, and history is preserved

`audit_draft`/`rollout` gained `objective` (and an internal `scorer`), defaulting to
`SEASON_LONG`. **Every pre-D103 measurement reproduces byte for byte**, pinned by
`test_default_rollout_is_unchanged_by_the_new_parameter`.

`WEEKLY_NO_FORESIGHT` reuses the already-tested
`weekly_objective.weekly_lineup_points_no_foresight` rather than introducing a new objective, and
**refuses to run without the weekly participation table** instead of silently falling back to a
different objective under the same name.

The test that establishes the two modes genuinely differ: two rosters differing **only** in which
backup QB occupies a bench slot score **identically** under season-long — the starter never vacates
the slot — and **differ** under weekly, because for the weeks the starter is absent the backup
actually plays.

**Which objective produced which number:** every D86 figure and every `SEASON_LONG` row below uses
season totals with one lineup allocation. Every `WEEKLY_NO_FORESIGHT` row sets the lineup each week
by preseason projection among that week's actual participants. Both are applied only to a finished
roster.

## 5. Part 3 — population, and one honesty note about D86

2021–2025 × slots **{1, 4, 7, 10}** × all 16 rounds × both shipped 1-QB formats = **320 audited
pick states per format per objective**, matching D86's 5 × 4 × 16 shape.

**D86's exact slot set is not recorded anywhere in the repository** — its runner was a scratchpad
script that no longer exists. `{1, 4, 7, 10}` was chosen to spread across the snake and was
declared in the runner's pre-registration before results were read. **A discrepancy against D86's
recorded mean regret of 116.2 is therefore expected and is not evidence of a defect.** Measured
here: 134.8 (target, season-long) — same order, different sample.

**Phase convention registered by this phase:** EARLY = 1–5, MIDDLE = 6–10, LATE = 11–16. This is
*not* the repository's previous convention — D102 proposed a four-segment split (1–4 / 5–8 / 9–12 /
13–16) reasoned from the 10-starter/6-bench roster, and neither had ever been measured. The
three-phase split is used because it is the registered one; **the full per-round table is reported
below so the four-segment reading is recoverable without re-running anything.**

## 6. Results — regret by phase and round

### target_league

| objective | all picks | EARLY (1–5) | MIDDLE (6–10) | LATE (11–16) |
|---|---|---|---|---|
| `season_long` | mean **134.8**, median 116.1, total 43 140 | **181.5** | 121.0 | 107.4 |
| `weekly_no_foresight` | mean **107.4**, median 87.9, total 34 362 | **162.5** | 89.1 | 76.7 |

Zero/near-zero regret: 2.2% (season-long), 3.4% (weekly). Alpha's pick **is** the oracle's in only
2.2% / 3.4% of picks.
Distribution (season-long): p10=48, p25=87, **p50=116**, p75=181, p90=237, p99=330, p100=413.

### dynasty_1qb

| objective | all picks | EARLY | MIDDLE | LATE |
|---|---|---|---|---|
| `season_long` | mean **141.8**, median 126.6, total 45 374 | **181.1** | 144.2 | 107.0 |
| `weekly_no_foresight` | mean **103.1**, median 90.4, total 33 003 | **147.6** | 98.1 | 70.2 |

### By round (mean regret)

| rd | target SL | target WK | dynasty SL | dynasty WK |
|---|---|---|---|---|
| 1 | 185.2 | 167.0 | 183.9 | 161.5 |
| 2 | **198.3** | **174.3** | 174.2 | 144.9 |
| 3 | 185.8 | 168.6 | **184.8** | 156.6 |
| 4 | 171.7 | 155.9 | 183.3 | 143.8 |
| 5 | 166.6 | 146.5 | 178.9 | 131.3 |
| 6 | 129.9 | 101.2 | 176.4 | 127.7 |
| 7 | 103.4 | 75.1 | 147.0 | 89.5 |
| 8 | 110.8 | — | 143.5 | 99.3 |
| 9 | 129.4 | — | 128.3 | 87.9 |
| 10 | 131.8 | — | 126.0 | 86.0 |
| 11 | 114.4 | — | 118.8 | 83.4 |
| 12 | 113.2 | — | 112.2 | 74.4 |
| 13 | 102.9 | — | 107.6 | 71.4 |
| 14 | 100.0 | — | 101.0 | 65.4 |
| 15 | 108.9 | — | 98.8 | 64.9 |
| 16 | 104.8 | — | 103.9 | 61.9 |

The candidate **spread** (best minus worst on the slate) decays monotonically — target season-long,
357.8 in round 1 to 133.6 in round 16 — closely reproducing D86's 343.7 → 113.0 on its own sample.

### Season-clustered contrasts (k = 5, the independent unit; exploratory)

| contrast | target_league | dynasty_1qb |
|---|---|---|
| EARLY − LATE, season-long | +74.2, CI [−4.6, +152.9] | +74.0, CI [−26.2, +174.2] |
| EARLY − LATE, weekly | **+85.7, CI [+16.5, +154.9]** | +77.4, CI [−11.9, +166.7] |
| WEEKLY − SEASONLONG, all | **−27.4, CI [−53.8, −1.0]** | **−38.7, CI [−59.9, −17.5]** |
| WEEKLY − SEASONLONG, early | −19.1, CI [−37.9, −0.2] | −33.4, CI [−60.4, −6.4] |
| WEEKLY − SEASONLONG, middle | −32.0, CI [−68.8, +4.8] | −46.1, CI [−75.6, −16.7] |
| WEEKLY − SEASONLONG, late | **−30.6, CI [−59.9, −1.3]** | **−36.8, CI [−62.9, −10.7]** |

Directionally consistent in all eight cells. With five clusters and several contrasts these are
reported as **exploratory**; no gate was invented and no threshold was chosen after the fact.

## 7. Part 4 — the questions this phase exists to answer

### A. Is regret concentrated early, middle, or late?

**Early, decisively and in every cell.** 181.5 / 121.0 / 107.4 (target, season-long) and 162.5 /
89.1 / 76.7 (weekly); dynasty 181.1 / 144.2 / 107.0 and 147.6 / 98.1 / 70.2. Under the weekly
objective the early phase carries **2.1×** the late phase.

This is mechanically sensible rather than surprising: the candidate spread at round 1 is ~358
points and at round 16 is ~134, so the opportunity to lose value is simply larger early. **It is
also the opposite of where a "late picks are wasted" intuition would look.**

### B. Does late-round regret stay near zero under a weekly objective — or was the old conclusion an artifact?

**Neither. Both halves of the question rest on a premise this phase refutes.**

- **Late regret was never near zero.** Under season-long it is **107.4** (target) and **107.0**
  (dynasty) — 59% of the early figure, not a rounding error. **D102's claim that season-long
  scoring makes late-pick regret "near-degenerate by construction" is wrong**, and the mechanism it
  invoked was wrong too: `compute_league_starters` allocates the best ten of sixteen *by season
  total*, so a late pick who turns out well does enter the lineup. What season-long cannot see is
  **insurance** value — covering a starter's missing weeks — not late-pick value as such.
- **Switching to weekly *reduces* late regret** (107.4 → 76.7; 107.0 → 70.2), it does not raise it.
  It reduces regret at **every** phase. The reason is that a weekly lineup adapts: swapping one
  player changes the summed weekly lineup less than it changes a single season-long allocation, so
  the weekly objective **compresses the spread between candidates**.

**So the experiment D102 recommended was run and its motivating hypothesis did not survive.** The
weekly objective is still the more faithful `U` — it is the one that can see a bye, an injury and
the bench, and D86 measured 17.8% of realized points arriving through it — but it makes every pick
matter *less*, rather than revealing hidden late-round value. That is reported as a contradiction,
not smoothed over.

### C. Systematic rounds where Y1 repeatedly chooses a meaningfully inferior candidate?

**Rounds 1–5, and round 2 above all** (198.3 target, season-long — the single worst round). Alpha's
pick equals the oracle's in **0%** of rounds 1–5 in both formats. The only rounds with any hits at
all are 6–8 and 11 (5–15%).

Read carefully, though: "never matches the oracle" in round 1–2 is close to inevitable when the
slate holds ~20 plausible candidates and outcome variance is enormous. §7D is what distinguishes
that from a decision defect, and it says most of this is not one.

### D. What causes the largest regrets?

| | target SL | target WK | dynasty SL | dynasty WK |
|---|---|---|---|---|
| oracle's player simply **scored more** (luck-shaped) | 95.5% | 92.9% | 95.2% | 92.1% |
| oracle's player scored **no more** and still won (**structural**) | 4.5% | 7.1% | 4.8% | 7.9% |
| **cross-position** error | 74.8% | 73.1% | 75.5% | 78.4% |
| within-position error | 25.2% | 26.9% | 24.5% | 21.6% |
| oracle's player's median rank on **Alpha's own board** | 73 | 34 | 102 | 51 |
| …in Alpha's top 5 | 10% | 16% | 7% | 12% |

Two things stand out.

**The oracle's winning candidate is usually a player Alpha rated very low** — median rank 73 of
~610 under season-long. A pick Alpha ranked 73rd turning out best is the signature of outcome
variance, not of a mis-ordered objective.

**Structural error is the small slice, and weekly makes it relatively larger.** Converting to a
per-draft quantity (20 drafts per cell):

| | structural picks/draft | mean regret | ~points/draft (upper bound) |
|---|---|---|---|
| target, season-long | 0.70 | 129.6 | **~91** |
| target, weekly | 1.10 | 97.8 | ~108 |
| dynasty, season-long | 0.75 | 114.7 | ~86 |
| dynasty, weekly | 1.20 | 94.2 | ~113 |

**The season-long figure independently reproduces D86's ~90 points per draft on a different slot
set** — a genuine replication, not a restatement. The weekly objective raises the *structural
share* (4.5% → 7.1%) even while lowering total regret, which is the one respect in which it does
what D102 hoped: it makes relatively more of the residual decision-shaped.

These remain **hypotheses about mechanism**, labelled as such. "Cross-position" and "structural"
are observable properties of the slate; they are not proof that a different objective would have
chosen better.

## 8. Part 5 — ORACLE_Y1 and the information/decision decomposition

D97's `ORACLE − PROD` could not isolate projection headroom because `ORACLE` carried perfect
information **and** the NAIVE rule. The missing cell is oracle information with the **Y1** rule.

**What ORACLE_Y1 is allowed to change** — established before running it, and pinned by test: the
`projections` and the VORP mathematically derived from them, **and nothing else**. The market board
(which drives the opponents and the survival term), the confidence/dispersion inputs, and the
consensus-board consumption demand are all held fixed, because changing those would alter the
*environment* or the *rule* rather than the information.

| format | PROD | ORACLE_Y1 | **information effect** (rule held at Y1) |
|---|---|---|---|
| target_league | 1983.6 | 2778.9 | **+795.3**, CI [+579.1, +1011.4], **5/5 seasons** |
| dynasty_1qb | 2094.9 | 2811.9 | **+717.0**, CI [+432.8, +1001.3], **5/5 seasons** |

Against D97's recorded `ORACLE − PROD` of +784.6 / +704.6, the implied **decision-rule effect under
oracle information** is about **−10.7 / −12.4 points** — indistinguishable from zero.

**This corrects D102.** D102 hypothesised that Y1's uncertainty machinery (survival, confidence,
opportunity cost) would be *actively harmful* once information was perfect, and that the
interaction could be large. **It is not.** The confound D102 identified is real in principle and
negligible in practice, which means **D97's reading of that residual as information-shaped was
close to right.**

Stated limits, because non-additivity is the thing this section exists to avoid pretending away:
D97's `ORACLE` was run on a different slot set (10 slots) from this phase's ORACLE_Y1 (4 slots), so
the ~11-point rule effect is a **cross-run difference, not a within-run measurement**. The clean,
within-run statement is the information effect alone. Getting the rule effect to the same standard
needs `ORACLE` re-run on these slots, which this phase did not do.

## 9. Part 6 — leakage sanity check

| surface | verdict |
|---|---|
| `assert_no_realized_inputs_in_policy()` | called before any measurement in every mode; run aborts on failure |
| projections into the policy | `static.projections` are Y1 projections; the rollout policy sees no outcome table |
| uncertainty / confidence / survival | derived from `market_snapshot` and pick geometry, not outcomes |
| opportunity cost, replacement | computed from projections and the available pool |
| opponent behaviour | `roster_aware_market_pick`, preseason ECR only |
| continuation policy | tier `L0`, pinned to production in §3 |
| realized outcomes | reach **only** the roster scorer, after every decision is made |
| candidate slate | includes the realized top-N — an **evaluation** input, never a policy input, and the reason measured regret is not biased toward zero |
| **ORACLE_Y1** | deliberately feeds outcomes into the policy's *inputs*. Quarantined in its own mode, writing its own artifact; a test asserts `oracle_static` is unreachable from the regret path |

## 10. Part 7 — decision versus information

> *When Y1 makes a materially suboptimal pick, is the evidence more consistent with A (bad
> information, correct decision), B (adequate information, wrong decision), C (both), or D
> (insufficient evidence)?*

**Predominantly A, with a small and persistent B, and an honest limit that keeps A from being
proven outright.**

- **For A:** 92–96% of divergences are cases where the oracle's player simply scored more; the
  oracle's winner sits at median rank 73/610 on Alpha's own board; and giving Y1 perfect
  information is worth **+795.3 / +717.0** with the rule unchanged, 5/5 seasons, CI excluding zero.
- **For B:** the structural residual is real and reproducible — 4.5–7.9% of divergences, ~86–113
  points per draft, replicating D86's ~90 — and it is **cross-position dominated** (75%), matching
  D86's finding that its dominant pattern was Alpha taking a QB where the oracle wanted a RB or WR.
- **The limit:** "the oracle's player scored more" **conflates bad information with unavoidable
  variance**. This instrument cannot separate "identifiable ex ante and our projection missed it"
  from "nobody could have known". So A is the best-supported category, not a demonstrated one, and
  no share of the 92–96% should be quoted as *projection* error.

C is not supported as a *balanced* mixture. D applies specifically to the A-versus-variance split.

**Projection metrics from D97–D101 are not used to reach this conclusion**, and none is a success
criterion here.

## 11. Part 8 — 2026

**Not run.** No specific hypothesis survived the 2021–2025 evidence that could be tested on 2026
without changing the registered measurement. The phase's purpose was to establish the measurement.

## 12. Part 10 — verdict and the seven plain answers

**Classification: D — NOT CONFIRMED.** The measurement is established, validated and reproducible;
what is not confirmed is any decision-rule opportunity worth pursuing. No production change.

1. **Are we now measuring the thing we actually care about — the quality of each draft decision?**
   **Yes, with a stated ceiling.** Per-pick regret against the best available candidate, under a
   fixed production continuation, on a leakage-guarded instrument now pinned to production, with a
   selectable and more faithful roster-value function. It measures one pick against a fixed
   continuation — a lower bound — not joint optimality.
2. **Where does Y1 lose value — early, middle, or late?** **Early.** 181.5 / 121.0 / 107.4
   (target, season-long); 162.5 / 89.1 / 76.7 (weekly). Monotone in all four cells; round 2 worst.
3. **Does weekly/no-foresight scoring materially change the previous late-round conclusion?**
   **Yes — and in the opposite direction to the one D102 predicted.** It *reduces* late regret
   (−30.6 / −36.8) and reduces regret at every phase. Late regret was never near zero, so there was
   no artifact of the kind D102 asserted.
4. **How much of the gap is information vs. decision rule?** Information dominates: **+795.3 /
   +717.0** with the rule held at Y1, 5/5 seasons. The decision-shaped residual is **~86–113 points
   per draft**, reproducing D86's ~90. Under oracle information the Y1 rule and the NAIVE rule are
   within ~11 points (cross-run, so indicative).
5. **Is there evidence that changing the decision algorithm itself would improve picks?**
   **No confirmed evidence.** The structural residual is real but is ~86–113 points against D97's
   ~172–250 point measurement floor — **below what any experiment this instrument can run could
   detect**. Ten value bases, a weekly objective and legality separation have now all failed.
6. **Is there evidence that projections/information are the binding problem?** **Yes for
   information in the sense of perfect foresight**, measured directly for the first time with the
   rule held fixed. **No** for the stronger claim that *achievable* projection improvement is
   worth pursuing — D100 bounded the reachable identification slice at +0.80 of 6 with 45% of the
   gap absent from the data, and nothing here changes that.
7. **Smallest defensible next experiment, if any?** See §13.

## 13. Recommended next phase (documented only; not started)

The honest reading of §12.5 and §12.6 together is that **both levers are now measured and both are
out of reach on this instrument** — the decision-shaped residual is below the detection floor, and
the achievable share of the information gap was bounded low by D100. That is a stopping point, not
a menu.

If one question is worth the next phase, it is the one the data actually points at rather than the
one that is easiest to run:

> **Of the +795.3 information effect, how much is reachable from information that existed at
> preseason?** ORACLE_Y1 uses realized outcomes — an upper bound on nothing achievable. Substituting
> the *best preseason-available* ranking already in the repository (the FantasyPros consensus board,
> which D100 measured as beating M6 on top-6 identification) in place of Y1 projections, with the
> rule held at Y1, would put a **floor** under the same contrast. The gap between that floor and
> +795.3 is the only honest estimate of what better projections could actually buy.

It reuses the ORACLE_Y1 machinery added here with a different substitution, needs no model, no
fitting and no new data. **It is recorded as a recommendation only; D104 is not started.**

Explicitly **not** recommended: O2/O3, another value base, a lookahead optimizer, re-tuning any
projection proxy, or any use of 2026.

## 14. Reproduction

```
uv run python scripts/research/d103_pick_regret.py --mode regret    --out <dir>
uv run python scripts/research/d103_pick_regret.py --mode oracle_y1 --out <dir>
uv run python scripts/research/d103_pick_regret.py --mode parity    --out <dir>
uv run pytest tests/unit/test_draft_oracle.py tests/unit/test_d103_pick_regret.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```
