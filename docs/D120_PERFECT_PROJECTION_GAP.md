# D120 — Why does Alpha leave oracle value on the table even with perfect projections?

**Headline: about half of the "~27% perfect-projection residual" was an instrument defect, not the
decision rule.** The ORACLE_Y1 arm fed perfect projections into the shipped rule but kept M6's
`confidence`. D117 showed that confidence is a function of the *old* projection, so the risk
multiplier kept penalising players by what Y1 had thought of them. Recomputing confidence at the
perfect projection, with M6's own formula, recovers **+19.8 points/pick** (CI [+8.8, +30.7]).
Recovery rises from **72.7% to 87.0%** (target) and **74.4% to 87.2%** (dynasty). The stale
replacement levels the docstring warned about are real but **have exactly zero effect**: the
shipped engine recomputes draft-aware levels at every pick, so ARM 2 picks what ARM 1 picks at all
640 states. **What remains under internally consistent perfect projections is ~13% of regret (~17–18
points/pick). That is a genuine decision-architecture gap**: 74% of it in rounds 1–6, 87–92% of it
a wrong-*position* choice (RB where the oracle wanted a WR or a QB), and driven by the value
base (~40% of the score gap) and the survival urgency term (~22–26%).

**Diagnostic only. No production change, no weight tuned, no formula changed beyond the mechanical
recomputation, no new information. Nothing ships.** `src/alpha_squad/` byte-identical (tree
`55e763e8…`).

---

## 1. Plain-English conclusion

* **Does the architecture still choose worse when it knows everything? Yes, but by about half as
  much as previously published.** With projections *and* every quantity derived from them made
  perfect and consistent, the shipped rule still leaves **13.0%** (target) / **12.8%** (dynasty) of
  per-pick regret: **17.8 / 16.8 points per pick**, season CI [4.8, 30.9] / [2.1, 31.6].
* **The other ~14 percentage points of the published residual were the instrument.** ORACLE_Y1
  changed the projections but left the risk multiplier reading the old ones. Those 14.4 pp
  (target) and 12.8 pp (dynasty) are an artefact of an internally inconsistent arm, not a property
  of the rule.
* **The remaining gap is early and positional.** It sits in rounds 1–6 (74% of it). It is almost
  entirely a wrong-position choice, not a wrong-player one. The largest flows are RB taken where
  the oracle wanted a WR (34% of the residual, target) or a QB (10% target, 24% dynasty). Even with
  perfect projections, the rule's own value base prefers its pick in ~63–65% of those states, and
  its survival multiplier pushes toward its pick in 73% (target) / 53% (dynasty).
* **What is fixable and what is not.** The stale-risk portion needs no fixing in *production*,
  because production's confidence is consistent with production's projections. It was a defect
  in the research arm only. The ~13% is structural: it would persist with a perfect projection
  model, so better projections cannot remove it. Whether it is *reachable* by any preseason-
  implementable rule is not established here (§7).

---

## 2. Instrument audit

### 2.1 Reproduction first (the stop condition)

ORACLE_Y1 was re-run through D103's unmodified `oracle_static` and D115's unmodified harness at
all **640 states**. Its pick **and** its one-step delta equal D115's stored `d115_arms.json`
(re-run on this vintage in D118) **at every state**; the runner raises on any mismatch. The
control rollout also equals D115's stored value at every state. **The existing arm reproduces
exactly, so the new arms are interpretable.**

### 2.2 Every projection-dependent input of the shipped L0 decision

The table compares ORACLE_Y1's static against a full rebuild from the perfect projections,
2021–2025, both formats. "Changed" counts players/positions whose value differs.

| input | where the shipped score reads it | ORACLE_Y1 updates it? | full rebuild vs ORACLE_Y1 | decision effect (measured, §3) |
|---|---|---|---|---|
| `projections` | everything below | **yes** | 0 changed | — |
| static `vorp` | opportunity cost (`positional_opportunity_cost`) | **yes** (it recomputes its own replacement level internally) | 0 changed | — |
| static `replacement_levels` | only a **fallback** inside `vorp_term` when the draft-aware level lacks a position | **NO: defect.** Its docstring says it is recomputed, but the code does not | all 6 positions, up to **55 points** (2023 RB 127 → 183) | **zero**: 0 of 640 picks change, and scores are unchanged to the last digit |
| static `scarcity_raw` / `scarcity_norm` | not read by the L0 score | no | all 6 positions | zero (ARM 4 ≡ full rebuild) |
| `confidence` (the risk multiplier) | `risk_mult = confidence or 0.7`, on every candidate | **NO**: it is read from M6's table, which no rebuild touches | 239–263 of ~450 players per season; max 0.77 | **large**: §3 |
| `consumption_demand` | draft-aware replacement demand | n/a (market-only) | 0 changed | none |
| draft-aware replacement, MSV, lineup baseline | recomputed from `static.projections` at every pick | **yes** | — | — |
| `market_rank`, `ecr_dispersion` (opponents, survival) | opponents, opportunity-cost replay, survival | n/a (market information, not projection) | identical | none |
| roster fit, feasibility cap, `availability_rates` | roster composition / prior seasons | n/a | identical | none |

**Two defects in the research instrument, neither in production:**
1. `oracle_static` does not recompute `replacement_levels`, contrary to its own docstring.
   **Measured consequence: none.** It is pinned by a regression test
   (`test_oracle_static_leaves_replacement_levels_stale`); D103 is not edited.
2. `oracle_static` keeps M6's `confidence`. D103 kept it deliberately, calling a change a "rule"
   question. But D117 established that confidence *is* a function of the projection
   (`clip(1 − width/(2·projection))`, exact to 0.0). Keeping it therefore feeds the risk term the
   *old* projection, so the arm is internally inconsistent. **Measured consequence: 14.4 pp of
   recovery (target) and 12.8 pp (dynasty).** Pinned by the same regression test.

**The full-rebuild audit check (ARM 4F)** rebuilds every static field from the perfect projections
and adds recomputed confidence. It picks **exactly** what ARM 4 picks at all 640 states. **No other
stale projection-dependent input affects any decision.**

---

## 3. The four diagnostic arms

Each arm's board is used only to choose the pick at each audited production state. D115's common
continuation (shipped policy on the Y1 board) scores it. k = 5 seasons (every season has perfect
information). The CI is season-clustered, and the MDE is its half-width (D114 convention).

### `target_league` (PRIMARY)

| arm | one-step Δ / pick | 95% CI | MDE | **recovery** (season-long) | weekly Δ / pick | **weekly recovery** | per-pick regret | changed vs control | changed vs ORACLE_Y1 | = per-pick oracle |
|---|---|---|---|---|---|---|---|---|---|---|
| ARM 1 ORACLE_Y1 as committed | +99.98 | [58.0, 141.9] | 42.0 | **72.7%** | +55.7 | 56.3% | 37.6 | 92.8% | 0% | 29.1% |
| ARM 2 + replacement levels | +99.98 | identical | | **72.7%** | +55.7 | 56.3% | 37.6 | 92.8% | **0%** | 29.1% |
| ARM 3 + confidence | **+119.75** | [78.7, 160.8] | 41.1 | **87.0%** | +74.4 | **75.2%** | **17.8** | 95.3% | **61.9%** | 47.2% |
| ARM 4 + both | +119.75 | identical to ARM 3 | | **87.0%** | +74.4 | 75.2% | 17.8 | 95.3% | 61.9% | 47.2% |
| *ARM 4F full rebuild (audit)* | *identical to ARM 4 at all 320 picks* | | | | | | | | | |

### `dynasty_1qb` (replication)

| arm | Δ / pick | CI | recovery | weekly Δ | weekly recovery | per-pick regret | changed vs ORACLE_Y1 |
|---|---|---|---|---|---|---|---|
| ARM 1 | +98.14 | [59.1, 137.2] | **74.4%** | +61.2 | 60.5% | 33.8 | 0% |
| ARM 2 | identical | | **74.4%** | | 60.5% | 33.8 | **0%** |
| ARM 3 / ARM 4 | **+115.08** | [73.4, 156.7] | **87.2%** | +72.8 | 72.0% | **16.8** | 42.8% |

The weekly per-pick oracle was produced here by `audit_draft(objective=WEEKLY_NO_FORESIGHT)` on
the identical grid. The arms run and the weekly audit are independent walks of the same drafts, and
they scored the control pick identically at every state (checked).

### By season (season-long recovery, ARM 1 → ARM 4)

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| target | 74.0% → 91.0% | 51.5% → 73.1% | 78.3% → 88.2% | 79.0% → 83.9% | 74.9% → 98.2% |
| dynasty | 84.0% → 93.8% | 67.6% → 78.2% | 57.8% → 71.6% | 86.1% → 97.6% | 72.3% → 91.0% |

**The confidence correction helps in all 10 season-format cells.**

### By round and position (target, per-pick arm regret, ARM 1 → ARM 4)

* **R1–6: 51.1 → 35.1 · R7–11: 37.2 → 7.9 · R12–16: 21.8 → 7.1.** Dynasty: 35.1 → 33.3,
  40.8 → 11.0, 25.2 → 2.9. The confidence correction mostly fixes the middle and late rounds; the
  early rounds keep most of their gap.
* By the oracle's position (target): RB 38.0 → **8.1**, WR 38.7 → 25.6, TE 19.3 → 13.2, **QB
  52.6 → 51.8, unchanged**. When the oracle wants a QB, the rule misses it with or without the
  correction.

---

## 4. Decomposition of the perfect-projection residual (measured, not assumed additive)

| component | target | dynasty | paired per-pick effect (season CI) |
|---|---|---|---|
| residual of ORACLE_Y1 as published | **27.3%** | **25.6%** | — |
| stale replacement-level effect: R(2) − R(1) | **0.0 pp** | **0.0 pp** | +0.00 (0 of 640 picks change) |
| **stale risk / confidence effect**: R(3) − R(1) | **14.4 pp** | **12.8 pp** | target **+19.8 [+8.8, +30.7]**, dynasty **+16.9 [+9.7, +24.2]** |
| interaction: R(4) − R(2) − R(3) + R(1) | 0.0 pp | 0.0 pp | ARM 4 − ARM 3 = +0.00 |
| **other decision residual**: 1 − R(4) | **13.0%** | **12.8%** | per-pick regret 17.8 [4.8, 30.9] / 16.8 [2.1, 31.6] |

**Share of the published residual each component explains:** stale risk explains **53%**
(target) and **50%** (dynasty); stale replacement levels explain **0%**; the decision rule explains
the remaining **47% / 50%**. Weekly, stale risk is +18.7 [+10.7, +26.7] (target) and +11.6
[−8.3, +31.5] (dynasty, unresolved), and the weekly residual after correction is 24.8% / 28.0%.

**Old and corrected results, kept separate.** D115 and D118 published ORACLE_Y1 at 73.5% / 72.7%
recovery, "~27% is a rule residual". **That number remains a correct measurement of the arm as
defined**, and it is not overwritten. **The corrected perfect-information ceiling of the Y1 rule
is 87.0% (target) / 87.2% (dynasty), and the rule residual is ~13%, not ~27%.** D119's "~37
pts/pick" rule residual is correspondingly ~17–18.

---

## 5. Residual attribution under internally consistent perfect projections (ARM 4)

These are existing categories only. ARM 4's pick P is compared with the per-pick oracle's player O
(D115). Sequencing uses D115's own `survives_counterfactual`. The score factors use D117's exact
Shapley split on the ARM 4 board.

| | target | dynasty |
|---|---|---|
| ARM 4 picks the oracle's player | 151 / 320 | 162 / 320 |
| total ARM 4 regret | 5,706 | 5,391 |
| **B: wrong position** | **125 picks, 87.2% of the residual** | **132 picks, 91.7%** |
| A: right position, wrong player | 44 picks, 12.8% | 26 picks, 8.3% |
| C1 ∧ C2: both obtainable (sequencing overlay) | 89 picks, 44.2% | 95 picks, 44.4% |
| **rounds 1–6 / 7–11 / 12–16** | **73.7%** / 13.8% / 12.5% | **74.1%** / 20.4% / 5.4% |
| legality override | 0 | 0 |

**Largest flows (ARM 4 pick → oracle's position, share of residual):**
- **target:** **RB → WR 33.9%**, WR → RB 10.5%, RB → QB 10.1%, QB → RB 7.5%, WR → WR 6.5%, WR → QB 5.6%.
- **dynasty:** **RB → WR 24.9%, RB → QB 23.8%**, QB → WR 11.5%, WR → RB 10.1%, QB → RB 8.4%.

**Which score factor made the rule prefer its pick over the oracle's (exact Shapley, share of the
P − O score gap):**

| factor | target share | favours P / O | dynasty share | favours P / O |
|---|---|---|---|---|
| **value** (MSV + draft-aware VORP) | **40.7%** | 106 / 63 | **39.7%** | 103 / 55 |
| **survival** (urgency multiplier) | **26.3%** | **124 / 27** | **21.9%** | 84 / 29 |
| roster fit | 12.8% | 82 / 21 | 11.8% | 98 / 13 |
| opportunity cost | 9.5% | 37 / 6 | 7.7% | 31 / 4 |
| risk (confidence, now consistent) | 6.6% | 85 / 81 | 8.1% | 99 / 58 |
| capacity | 4.2% | 7 / 0 | 10.8% | 24 / 0 |

Reading: with perfect projections the value base still prefers the rule's pick in roughly two of
three residual states. It values the candidate *now* (marginal starter value plus VORP against the
current draft-aware level), whereas the oracle values the whole roster the continuation goes on to
build. The survival multiplier then pushes further toward the rule's pick in 124 of 169 (target) and 84 of 158
(dynasty) of those states: it adds urgency to the player likely to be gone, whether or not that player is the
better roster addition. Roster fit and opportunity cost add a little each. No single term is the
whole story; **value + survival carry 67% (target) / 62% (dynasty) of the gap.**

---

## 6. Structurally fixable vs information-dependent

| piece of the per-pick regret (target, 137.6 pts/pick on this vintage) | share | nature |
|---|---|---|
| recovered by perfect information through the rule (ARM 4) | **87.0%** | **information-dependent**: requires knowing outcomes; D115–D119 found no preseason signal that moves it detectably |
| stale-confidence artefact in ORACLE_Y1 | (14.4 pp, now inside the 87%) | **an instrument defect**, not a production issue: production's confidence is consistent with its own projections |
| **decision-rule residual under consistent perfect information** | **13.0%** (~18 pts/pick) | **structural**: independent of projection quality; early-round, cross-position; value base + survival urgency |

* **Structural (decision rule):** the ~13%. It is measurable (CI excludes 0 in both formats) and
  it would persist with a perfect projection model.
* **Information-dependent:** everything else, ~87% of the per-pick regret. D116–D119 showed
  Alpha's stored preseason information cannot reach it detectably.
* **Not established:** that the 13% is reachable by a rule that cannot see outcomes. Part of it
  may be intrinsic to any one-step heuristic, because the per-pick oracle is a slate maximiser
  that sees how the continuation responds. The 18 / 42 picks where ARM 4 beats that oracle (it
  picked outside the slate) show the oracle is not a perfect ceiling either.

---

## 7. Recommended next research question (exactly one)

> **In the early-round (R1–6) wrong-position states where the rule, even with perfect projections,
> takes an RB over the oracle's WR or QB, does the shipped VALUE BASE (marginal starter value +
> draft-aware VORP) rank the candidates differently from their actual one-step roster value, and
> how much of that disagreement is the myopic "value now" construction versus the survival
> multiplier's urgency?**

It targets the only structural piece left, ~18 pts/pick, measurable and concentrated in one phase
and one kind of decision. It can be answered by attribution on existing instruments (the ARM 4
states, D117's factorisation, D115's rollouts) with no new model, no new information and no
tuning. It is also the precondition for any rule change: if the value base and roster value
disagree in a consistent direction, that direction is the hypothesis a future pre-registered arm
would test. If they don't, the residual is one-step-heuristic noise and the programme can stop
spending phases on the rule.

---

## 8. Reproducibility, provenance and what changed

```bash
# inputs: D115 regret / timing / arms on this vintage (docs/D116 §9, docs/D118 §9)
R=scripts/research/d120_perfect_projection_gap.py
uv run python $R --mode audit  --out <o>
uv run python $R --mode arms   --leagues target_league --d115 <t> --out <o>   # ~7 min
uv run python $R --mode arms   --leagues dynasty_1qb   --d115 <d> --out <o>
uv run python $R --mode weekly --leagues target_league --d115 <t> --out <o>   # ~25 min
uv run python $R --mode weekly --leagues dynasty_1qb   --d115 <d> --out <o>
uv run python $R --mode report --out <o>
uv run pytest tests/unit/test_d120_perfect_projection_gap.py
```

| item | value |
|---|---|
| HEAD at run time | `aefb9be17442fd09b60cf0ac067cb290cc703591` (D119) |
| `src/alpha_squad` tree / dirty | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` / **False** |
| board vintage | `f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f` (= D116–D119; every input checked) |
| per season | 2021 `79599ffa…` 2022 `43f0e968…` 2023 `aa73cd3f…` 2024 `7873284c…` 2025 `0b344c7e…` |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| models | `uncertainty_catboost_v2` (M6), `rookie_features_v1` (M7); tier `L0`; opponent `market_consensus_roster_aware` |
| inputs: D115 regret / timing / arms (target) | `6d395458…` / `a8b44df6…` / `b259beba…` |
| inputs: D115 regret / timing / arms (dynasty) | `ee4921c5…` / `72308875…` / `72c5d74c…` |
| outputs `d120_audit` / `d120_arms_target` / `d120_arms_dynasty` | `1117effd…` / `f032a3d1…` / `258d3b5f…` |
| outputs `d120_weekly_target` / `d120_weekly_dynasty` / `d120_summary` | `418827e5…` / `2c15d75f…` / `424804c5…` |

**Files changed by D120 — research only:**

| file | status |
|---|---|
| `scripts/research/d120_perfect_projection_gap.py` | **new**: audit, arms, weekly oracle, report |
| `tests/unit/test_d120_perfect_projection_gap.py` | **new**: 17 tests, incl. the instrument-defect regression tests |
| `docs/D120_PERFECT_PROJECTION_GAP.md` | **new**: this report |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended; earlier entries not edited |
| `scripts/research/d103_pick_regret.py` | **unchanged**: the defect is documented and pinned, not silently repaired |
| `src/alpha_squad/**` | **unchanged** |
