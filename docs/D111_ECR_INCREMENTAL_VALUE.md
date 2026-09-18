# D111 — Does ECR add incremental information that improves Alpha's actual draft decisions?

> **§1 is the pre-registration. It was committed before any treatment arm was run.** Results begin
> at §4. Nothing in §1–§3 was edited after a treatment number was seen; corrections, if any, are
> appended as marked notes rather than made silently.

**Verdict: B + D, UNRESOLVED AND UNDERPOWERED.** Adding ECR to Y1 as a co-equal information source
is **positive in all four pre-registered primary cells** (+21.4 and +80.1 in `target_league`, +88.9
and +72.1 in `dynasty_1qb`) — a sign consistency D104 never achieved — but **every one sits below
the pre-registered 172–250 detection floor**, so all four are **UNRESOLVED** by the rule fixed in
advance. 56.8% of picks change. At the *player* level 57.9% of changed picks improve; at the
*roster* level only **36.7%** do, and **31.8% make literally no difference at all**.

**The most useful result is a reversal by draft phase.** Measured with a matched counterfactual
that holds the board and the continuation fixed, ECR's changed picks are worth **+24.1 early,
+16.6 middle and −8.7 late** per pick. Player-level scoring says the opposite, because a late-round
player who scores more individually still never reaches the lineup.

**The only effect in this phase that clears the detection floor is not about information at all.**
Giving a pure-ECR drafter the end-of-draft mandatory-slot rule is worth **+241.1 (target) / +215.3
(dynasty)**, 5/5 seasons, t ≈ 14–15 — five to ten times any ECR information effect measured here.

**No production change. No model fitted. No ECR weight tuned against outcomes. No 2026. Nothing
merged. No PR. Risk/uncertainty deliberately frozen and explicitly NOT closed.**

---

## 0. The question, and the one this is not

Does giving Alpha ECR **in addition to** its existing Y1 information produce better actual draft
decisions, pick by pick? The primary contrast is

    Y1 + ECR   vs   Y1

It is **not** "is ECR a better ranking than Y1" — D100 and D104 answered that — and ECR-alone is
carried here only as an **independent benchmark**, never as a target Alpha must beat.

D104 measured ECR **replacing** Y1's ordering. D111 measures ECR **added to** it. Those are
different experiments and the second does not follow from the first.

### What Y1 already does with ECR — established by inspection, before any arm was defined

The shipped decision rule (tier `L0`, `evaluation/draft_forensics.py::score_candidate`) is

    score = (msv + 1.0 * vorp + opp_cost) * fit_mult * risk_mult * survival_mult

and **two of those terms already read the ECR board**:

| term | how it reads ECR |
|---|---|
| `opp_cost` | `league/opportunity_cost.py::positional_opportunity_cost` replays the opponent model forward, and that model is literally `best_by_market_rank` — ECR |
| `survival_mult` | `_survival_probability` reads `ecr_best`/`ecr_worst` from the same preseason snapshot |

So Y1 **already consumes ECR as a timing model** — who will be gone, and when. What it has never
consumed is ECR as a **value opinion**: the opportunity cost is denominated in Y1's own VORP
points, and ECR only decides *which* player leaves the pool, never what he is worth.

**That is the precise incremental question D111 tests: does ECR's opinion about player VALUE add
anything, given Y1 already uses ECR's opinion about player AVAILABILITY?** It is stated here
because a phase reporting "ECR adds nothing" without it would be badly misleading.

---

## 1. Pre-registration

The full text also lives in the runner's module docstring
(`scripts/research/d111_ecr_incremental.py`), which is the repository's D39/D54/D55 convention —
the decision rule is committed to source before it meets real data.

### 1.1 Phase 0 — the integration methods, with measured grounds

Seven insertion points were enumerated and five rejected **before any arm was run**.

| # | method | decision | grounds |
|---|---|---|---|
| **M1** | **Board-level rank consensus.** Within position, re-assign Y1's own projected values to players ordered by the equal-weight mean of Y1's ordinal rank and ECR's ordinal rank | **ACCEPT — PRIMARY** | Parameter-free by symmetry at w = ½ (Borda / mean-rank is the unique symmetric combination of two orderings, and is what "expert consensus" *means* — FantasyPros' own ECR is an equal-weight mean of expert ranks). ECR enters the **information** layer, so its opinion propagates through msv, VORP, replacement level and opportunity cost exactly the way Y1's own does |
| **M2** | **Decision-level rank consensus.** Y1's engine untouched; it produces its ranked candidate list, ECR ranks the same candidates, the pick is the argmin of the equal-weight mean rank | **ACCEPT — SECONDARY** | Same Borda argument, different insertion point: ECR is a co-equal **voter on the decision** rather than an input to the valuation. Carried because a null at one insertion point is not a null at the other |
| M3 | ECR breaks exact ties in the decision score | **REJECT — measured no-op** | The minimal conceivable additive use, needing no coefficient at all, so it was *measured* rather than argued: across 192 real pick states the top score is exactly tied in **0** of them |
| M4 | An additive ECR term, `score += k · f(ecr_rank)` | **REJECT** | `k` is a points-denominated coefficient with nothing in the repository to derive it from. The brief forbids inventing one and forbids fitting one against outcomes; there is no third option |
| M5 | A multiplicative ECR factor | **REJECT** | M4's reason, plus it would compose with `risk_mult`, which this phase freezes |
| M6 | Points-domain average with `ecr_implied_baseline` | **REJECT** | D104's three grounds, each **re-measured on this vintage** — see §1.2 |
| M7 | Cross-position (overall) ECR consensus | **REJECT as an arm; recorded as follow-up** | It changes each position's value multiset, so replacement levels, scarcity and the positional value scale move with it — an information change confounded with a valuation change. It is exactly D108 reopening-criterion 3's untested axis and belongs there, not smuggled in here |

**Conclusion: exactly two methods are defensibly pre-registrable, M1 and M2.** Neither introduces a
coefficient that is not fixed by symmetry. Had none survived, the pre-registered instruction was to
stop and report that instead of forcing an experiment.

### 1.2 Why `ecr_implied_baseline` is not the vehicle — re-measured, not cited

`models/baselines/market_implied.py::ecr_implied_baseline` is the repository's existing ECR→value
transformation (walk-forward isotonic rank→points). D104 rejected it on three grounds; all three
were re-measured on **this** vintage rather than quoted:

**(a) It destroys the ordering under test.** Distinct values among the top 24 by value, 2023:

| position | distinct values in top 24 | largest tie group | D104 recorded |
|---|---|---|---|
| RB | **4** | **12** | 4 / 12 |
| WR | 7 | 6 | 6 / 6 |
| QB | 9 | 8 | 9 / 8 |
| TE | 12 | 4 | 12 / 4 |

The engine sorts `(-score, player_id)`, so an arm built on this chooses among 4–12 tied players
**alphabetically**, precisely in the rounds D103 measured regret to be concentrated in.

**(b) It is hardcoded to `ecr_type='ro'`** (`_preseason_ranks_for_season`) and ignores the league's
resolved series, so `dynasty_1qb` (series `do`) would be fed the **redraft** board — a D56
violation costing half the population.

**(c) Coverage is 68.2%** of the 2023 draft board and only QB/RB/WR/TE, so substituting it changes
the candidate universe and breaks the pool parity the comparison depends on.

It is also a **valuation** change, not an information change: it moves each position's value
multiset, and with it the replacement levels.

### 1.3 The three systems

| | arm | definition |
|---|---|---|
| **CONTROL** | `Y1` | the shipped decision path, tier `L0`, unmodified |
| **TREATMENT** | `T1_ALL_w50` (M1, primary), `T2_w50` (M2, secondary) | Y1 **plus** ECR. Y1 is not replaced: at the registered weight each source carries equal say and Y1 keeps its entire value scale, replacement logic and decision rule |
| **BENCHMARK** | `ECR_ALONE` | our seat drafts `roster_aware_market_pick` — best available by preseason ECR, subject to the same end-of-draft mandatory-slot rule the nine opponents already use. ECR determines the selection directly; it is **not** run through Y1. `ECR_ALONE_NAIVE` (`best_by_market_rank`, no roster rule) is reported beside it |
| *context* | `ORACLE_Y1` | D103's hindsight cell, re-measured on this vintage. An information **ceiling**, nowhere described as achievable |

### 1.4 The weight, and why a ladder is not an optimization

The pre-registered **primary weight is w = 0.5** for both methods, fixed by the symmetry argument
and by nothing else. **The verdict is read off w = 0.5 and only w = 0.5.**

A ladder w ∈ {0, 0.25, 0.5, 0.75, 1.0} is also run and reported in full, as a **shape diagnostic**
in the style of D105's α-ladder. It is not a search — the winning rung is never promoted, the
primary is fixed in advance, and both endpoints are identities that validate the instrument:

- **w = 0 is provably Y1 itself**, asserted at runtime at every pick state (parity check P2);
- **w = 1 under M1 restricted to QB/RB/WR/TE is D104's `ecr_ordered_static` exactly** — carried as
  `T1_SKILL_w100`, the explicit bridge back to D104's arm.

The ladder is the only way to see whether an effect is monotone in how much ECR is trusted, which a
single point estimate cannot show.

### 1.5 Position set — and a correction to D104

M1's primary permutes **all six positions** (QB/RB/WR/TE/K/DST). D104 restricted itself to
QB/RB/WR/TE on the stated ground that *"K/DST, which no ECR board ranks"*. **That is not true of
this data**, measured: `ro`/`redraft-overall` carries 30–37 ranked kickers and 31–32 ranked
defenses in every season 2021–2025, and `do`/`dynasty-overall` carries 29–35 and 32.

D104's own §5 flags the consequence as an honest confound — holding K/DST fixed while skill values
move pulls the engine toward kickers, which is where its RB→K, WR→K and TE→K swaps come from.
Permuting every position removes that confound at the source. This is a **correction to D104's
stated justification**, not to its numbers.

### 1.6 Information / anti-leakage

| | |
|---|---|
| source | DynastyProcess `fp_ecr_history` (mirror of FantasyPros) → `market_snapshot` |
| series | the league's **resolved** `(ecr_type, page_type)` pair (D56): `target_league` → `ro`/`redraft-overall`, `dynasty_1qb` → `do`/`dynasty-overall`. Never hardcoded |
| vintage | **July/August scrapes of the target season only**, latest per player (D54) |
| identity | canonical `asq_` ids via `player_id_map`'s `fantasypros_id` bridge; never names |
| board read | `SeasonStatic.market_rank` — the same board the opponent model and the survival term already consume, so the treatment cannot see a board the control cannot |
| never | a later ECR ranking, a different date, or another season's board |

`assert_no_realized_inputs_in_policy()` runs before any measurement in every mode. Realized points
enter only the roster scorer, after every decision has been made — except in `ORACLE_Y1`, which is
quarantined behind its own arm name for exactly that reason.

### 1.7 Population, mechanics, continuation

2021–2025 × slots {1, 4, 7, 10} × both shipped 1-QB formats (`target_league`, `dynasty_1qb`) = 20
drafts per arm per format. **Seasons are the independent clusters (k = 5).** 2020 and 2026 are
refused outright.

Continuation policy unchanged in every arm: nine opponents draft `roster_aware_market_pick` off the
**control** board, the snake geometry is `draft_order(league)`, and the roster is scored by
`compute_league_starters` on realized points. In the matched-counterfactual mode the continuation
after the audited pick is the **control** board and the shipped engine for *both* candidates — D106
established that an arm-relative oracle is uninterpretable, so nothing here is scored against a
board that moved with the arm.

### 1.8 Metrics

- **Primary: realized whole-draft starter points** (`season_long`), season-clustered.
- Secondary: % of picks changed; % improved / worsened by realized value; mean and median realized
  change on changed picks; the gain/loss distribution; per round, per pick range (1, 20/21, 40/41,
  60/61), per position, per phase (EARLY 1–5 / MIDDLE 6–10 / LATE 11–16 — D103's registered
  convention); within- vs cross-position changes; the weekly objective (`weekly_no_foresight`).
- Pick-level regret is **not** used as a primary metric and arm-relative regret is not used at all
  (D106).

### 1.9 Detection floor, test, stopping rule, invalid cells

- **Detection floor:** D97's measured 172–250 points for a draft-level contrast, quoted not
  re-derived, and it is the pre-registered decision boundary — an effect below it is **UNRESOLVED**
  even if its point estimate is positive. The **realized MDE** is also computed and reported as
  `(t₀.₀₂₅,₄ + t₀.₂₀,₄) · sd/√5 = 3.717 · sd/√5`. "Not statistically significant" is never reported
  as "ECR has no value" without that number beside it.
- **Test:** season-clustered paired *t* on the per-season mean paired difference, k = 5, two-sided,
  t_crit = 2.776; 95% CI with every effect; per-season W/T/L so a result resting on one season is
  visible. No subgroup is promoted to primary after the fact.
- **Stopping rule:** **one** run of the registered grid. No slot added after seeing results (D88:
  slots cannot lower the floor — seasons bind), no season added, no weight promoted, no arm
  re-specified. If the primary is below the floor the phase reports UNRESOLVED and stops; no
  production run, no 2026, no retraining, no tuning follows.
- **Invalid cells.** A (format, season) cell is invalid, excluded and reported as excluded if
  (a) the resolved series has no preseason (Jul/Aug) board — `market_rank` empty; (b) fewer than 2
  ECR-covered players exist at a position the permutation would touch, for that position only;
  (c) `load_season_projections` returns no board, or none at a position the league must start.
  **No cell is ever repaired by substituting another date, another page or a later ranking.**

### 1.10 What this phase does not touch

Risk and uncertainty are **frozen**. `risk_mult` is not modified, removed, recalibrated or jointly
varied with anything here, and no new uncertainty estimate is built. The open question —

> **Can a properly constructed player-level / heteroscedastic uncertainty measure improve realized
> draft value?**

— is recorded as an explicit future research question and is **not** closed by this phase.

No production change. No model fitted. No ECR weight tuned against outcomes. No 2026. Nothing
merged. No PR.

---

## 2. The vintage problem, resolved before any arm was interpreted

**The board vintage has moved.** Every phase D97–D108 was measured at combined_hash
`ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99`; a from-source rebuild in this
environment produces `63076e2e2bbfbbe5c29fb41265966ac1b8aaa180b3e89ee7742388fcc19d98ad`. D108
reopening-criterion 5 calls that an instrument-integrity failure, so it is resolved here **before**
any treatment arm is read, not explained away afterwards.

### 2.1 The ECR half is bit-identical

The upstream board blob at the pinned commit (`D89_BOARD_COMMIT = 9338630`, sha256
`a966176d…`) was re-fetched and compared row by row against today's, over exactly the population
under test — `ecr_type ∈ ('ro','do')`, months 7–8, seasons 2021–2025:

| | rows | players | date range | sha256 of `(id, date, ecr_type, page_type, pos, ecr, best, worst)` |
|---|---|---|---|---|
| D89-pinned blob | 69,639 | 2,415 | 2021-07-02 … 2025-08-29 | `c5cfbbeb17aabbf9b903ab55051984f735c4c03daca75a6328272144d378fb7f` |
| today's blob | 69,639 | 2,415 | 2021-07-02 … 2025-08-29 | `c5cfbbeb17aabbf9b903ab55051984f735c4c03daca75a6328272144d378fb7f` |

**Identical.** The identity map (`db_playerids.csv`) differs over that population by exactly **one
added row — Jack Kiser, an LB**, irrelevant to a fantasy board — and **zero changed rows**.

**So D111's treatment signal is the information D104 measured.** D92's append-only property holds.

### 2.2 The projection half moved

`compute_board_vintage`'s combined hash is a hash of `load_season_projections`, so the entire delta
is in **Y1's own board** — downstream of the upstream nflverse restatement and, to a much smaller
degree, of the identity map. Board sizes per season (2021–2025): 636 / 651 / 610 / 602 / 629, with
ECR-covered counts 490 / 496 / 484 / 515 / 480 against D104's recorded 496 / 500 / 481 / 549 / 488.

**Consequence, stated in advance: absolute levels will not match D104's, and any comparison that
pretends otherwise is invalid.** D104's own decomposition is therefore re-run on this vintage
(`T1_SKILL_w100` *is* its `FP_ECR_Y1`) so the phase reports a same-vintage replication of the
number it builds on, rather than comparing across boards.

### 2.3 A small discrepancy in the D92 record, noted in passing

`D89_BOARD_SHA256` matches commit `9338630`'s `db_fpecr.parquet` exactly. `D89_IDMAP_SHA256`
(`0174ea89…`) does **not** match that commit's `db_playerids.csv` (`a02b7dc2…`), so the two pinned
hashes were captured from different fetches of a moving `master`. `board_vintage.py`'s docstring
only ever claims the commit for the *board*, so nothing published is wrong — but the idmap pin is
not commit-addressable and should not be treated as if it were.

---

## 3. Baseline parity — P1…P5

Parity was run and had to pass **before** any treatment arm was interpreted.

| | check | result |
|---|---|---|
| **P1** | tier `L0` picks identically to tier `H` (a direct pass-through to production's `recommend_draft_pick`) at every pick state of every registered draft. This is what makes the control production-equivalent | **640/640** — exactly D107's recorded figure, reproduced on the new vintage |
| **P2** | every arm at w = 0 is **byte-identical** to Y1 — the projection dict, the VORP dict and the chosen player, at every pick state. An arm differing from the control by anything other than the pre-registered ECR input fails here | **1300/1300** |
| **P3** | every treatment preserves each position's value multiset exactly (`SubstitutionError` otherwise), so replacement levels, scarcity and consumption demand are unchanged | **20/20** (a violation raises, so reaching the end *is* the pass) |
| **P4** | pool parity: the candidate universe is identical in every arm | **20/20** |
| **P5** | the ECR board of §2.1 reproduces | assembled board 68,870 rows, sha256 `9380096cd7c74427…`; upstream population hash identical to the D89 pin |

**PARITY: PASS.** It was run to completion and read *before* any treatment number was read.

Two further instrument checks fall out of the arms themselves and both hold exactly:

- **`T2_w100` and `ECR_ALONE_NAIVE` produce identical numbers** in every cell (−209.5 target,
  −275.8 dynasty), which is the algebraic prediction: the decision-level consensus at full ECR
  weight *is* best-available-by-ECR over the scored slate.
- **`T1_SKILL_w100` is D104's `FP_ECR_Y1`**, asserted against D104's own committed function by
  `tests/unit/test_d111_ecr_incremental.py`.

### 3.1 D104 replicates on a restated Y1 board

| contrast | D104 published (`ca3e2d8a`) | D111 re-measured (`63076e2e`) |
|---|---|---|
| `FP_ECR_Y1 − Y1`, target | **+77.3** | **+79.4** |
| `FP_ECR_Y1 − Y1`, dynasty | **−132.1** | **−74.9** |
| `ORACLE_Y1 − Y1`, target | +795.3 | **+772.4** |
| `ORACLE_Y1 − Y1`, dynasty | +717.0 | **+771.0** |

Same signs throughout, and the target-format ECR effect lands within 2.1 points of the published
figure on an independently rebuilt projection board. D104's null is not a vintage artifact.

---

## 4. Results

All effects are season-clustered paired differences (k = 5, t_crit = 2.776), 2021–2025 × slots
{1, 4, 7, 10} × 20 drafts per arm per format. **No cell was invalid**: every (format, season) pair
had a populated preseason board, every scrape fell inside July/August of its own season, and no
position fell below the two-player minimum.

### 4.1 The primary contrast — Y1 + ECR vs Y1

`season_long`, the registered primary objective. **Both primary arms, both formats:**

| format | arm | effect | 95% CI | seasons | realized MDE | vs floor |
|---|---|---|---|---|---|---|
| target | **T1_ALL_w50** (board consensus) | **+21.4** | [−100.3, +143.0] | 3W/2L | 162.9 | **UNRESOLVED** |
| target | **T2_w50** (decision consensus) | **+80.1** | [−23.9, +184.2] | 4W/1L | 139.4 | **UNRESOLVED** |
| dynasty | **T1_ALL_w50** | **+88.9** | **[+5.5, +172.2]** | **5W/0L** | 111.6 | **UNRESOLVED** |
| dynasty | **T2_w50** | **+72.1** | [−248.7, +392.8] | 3W/2L | 429.5 | **UNRESOLVED** |

**All four point estimates are positive.** That is the first time in this program that an ECR
intervention has not flipped sign across the two shipped formats. One cell — the board-level
consensus in dynasty — has a CI excluding zero and wins in 5 of 5 seasons.

**It is still UNRESOLVED, and the pre-registered rule is what says so.** +88.9 is below the
172–250 floor. A nominally significant result below the instrument's measurement floor is exactly
the case the floor exists to catch, and promoting it would be the error D104's stopping rule was
written to prevent.

The same four cells under the secondary objective:

| format | arm | `weekly_no_foresight` | 95% CI | seasons |
|---|---|---|---|---|
| target | T1_ALL_w50 | −4.3 | [−97.9, +89.3] | 3W/2L |
| target | T2_w50 | +93.3 | [−12.8, +199.5] | 4W/1L |
| dynasty | **T1_ALL_w50** | **+59.7** | **[+6.0, +113.3]** | **5W/0L** |
| dynasty | T2_w50 | +13.7 | [−261.1, +288.4] | 3W/2L |

Three of four remain positive, and **the one cell whose CI excludes zero does so under both
objectives, in the same format, 5/5 seasons each time.** That is the single most durable signal in
the phase — and it is still below the floor.

### 4.2 The ladder — ECR is worth more as a partner than as a replacement

The pre-registered shape diagnostic. **The primary is w = 0.50 and only w = 0.50; no other rung is
promoted.**

`season_long`, effect vs Y1:

| format | method | w=0.25 | **w=0.50** | w=0.75 | w=1.00 |
|---|---|---|---|---|---|
| target | T1 board | +38.1 | **+21.4** | +49.1 | +84.2 |
| target | T2 decision | +95.7 | **+80.1** | +32.1 | **−209.5** |
| dynasty | T1 board | +38.7 | **+88.9** | +44.9 | −87.2 |
| dynasty | T2 decision | +103.0 | **+72.1** | −94.5 | **−275.8** |

`weekly_no_foresight`:

| format | method | w=0.25 | **w=0.50** | w=0.75 | w=1.00 |
|---|---|---|---|---|---|
| target | T1 board | −0.8 | **−4.3** | +35.2 | +42.8 |
| target | T2 decision | +69.3 | **+93.3** | +16.6 | **−246.8** |
| dynasty | T1 board | +30.0 | **+59.7** | −7.9 | −164.8 |
| dynasty | T2 decision | +78.2 | **+13.7** | −135.3 | **−279.2** |

**In 6 of the 8 ladders the maximum is at an interior rung, and in 7 of 8 the w = 1 endpoint is
below the best interior rung.** The exception is T1/target, which rises monotonically. Where the
endpoint collapses it collapses hard — −209.5 to −279.2, the largest effects in the phase.

Read carefully, because the individual rungs are unresolved: what the ladder shows is a **shape**,
not a magnitude. The shape says ECR's value to Alpha is greatest when ECR is a *minority or equal*
partner and falls, often sharply, when ECR *displaces* Y1. That is the signature of incremental
information, and it is invisible to an experiment that only measures the endpoint — which is all
D104 did.

### 4.3 What changed, and did it get better?

Pooled over the four pre-registered primary cells (2 methods × 2 formats):

| | |
|---|---|
| picks changed | **727 / 1280 (56.8%)** |
| **player-level** — arm's player scored more | **57.9% improved**, mean **+10.9** realized points |
| **roster-level** — matched counterfactual | **36.7% better, 31.5% worse, 31.8% exactly neutral**, mean **+7.2** |

**Those two rows are the finding.** "The changed player scored more" happens in 58% of cases; "the
roster was worth more by the end of the draft" happens in 37%, and a third of all changed picks
move final roster value by *nothing at all*. The matched counterfactual is the instrument to
believe: it holds the state, the board and the continuation fixed and varies exactly one player, so
the difference is attributable to that pick and nothing else.

Per-arm, `target_league`, the two views side by side:

| arm | picks changed | player-level improved | roster-level better | roster-level mean |
|---|---|---|---|---|
| T1_ALL_w50 | 142/320 (44.4%) | **73.9%** (mean +17.7) | **38.0%** | **+0.0** |
| T2_w50 | 203/320 (63.4%) | 54.2% (mean +9.1) | 33.0% | +8.5 |
| ECR_ALONE | 291/320 (90.9%) | 51.2% (mean +9.4) | 43.3% | +8.1 |

`dynasty_1qb`:

| arm | picks changed | player-level improved | roster-level better | roster-level mean |
|---|---|---|---|---|
| T1_ALL_w50 | 166/320 (51.9%) | 54.2% (mean −0.7) | 44.6% | +6.5 |
| T2_w50 | 216/320 (67.5%) | 53.7% (mean +17.0) | 33.3% | +11.3 |
| ECR_ALONE | 303/320 (94.7%) | — | 40.9% | −0.2 |

The target/T1 row is the cleanest single illustration in the phase: **73.9% of changed picks took a
player who scored more, and the net effect on the roster was +0.0.**

Every season-clustered per-pick CI spans zero (+1.35, +7.52, +7.96, +7.03, +13.65, −0.04), so the
pick-level result is unresolved too — in the same direction as the primary.

### 4.4 Where ECR helps, and where it hurts

Matched counterfactual, pooled over the four primary cells:

| phase | n | mean delta per changed pick | better % |
|---|---|---|---|
| **EARLY (rounds 1–5)** | 163 | **+24.1** | 52.8% |
| **MIDDLE (rounds 6–10)** | 246 | **+16.6** | 41.9% |
| **LATE (rounds 11–16)** | 318 | **−8.7** | **24.5%** |

Sign-consistent across all six arm × format cells: early positive in 6/6, middle positive in 5/6,
**late negative in 6/6**.

**The player-level view says the opposite**, and the disagreement is the point. Under player
scoring, target/T1's late rounds look excellent — 60.8% of picks change, 72.6% improve. Under
roster scoring the same picks are worth −7.4 each. A late-round player who scores more individually
still never reaches the lineup; swapping him in displaces someone who would have. That is D86's
"the bench is priced at zero" arriving from a new direction, and it is why pick-level metrics that
score the *player* rather than the *roster* must not be used to justify a draft change.

By pick range (target, T1_ALL_w50): pick 1 changes in 1/5 drafts (+134.9); picks 20–21 in 3/10
(−36.9); picks 40–41 in 0/10; picks 60–61 in 6/10 (+44.7). Round 1 and round 2 changes are the
worst single rounds in the divergence table (−51.2 and −112.4 player-level), on small n.

By position, roster-level (pooled direction across the primary cells): the positive cells are QB
and RB in the decision-consensus arms and TE/DST in the board arm; the consistently negative cells
are **K (14.6–34.4% better) and DST late**. No position is sign-consistent across all four primary
cells, so no positional claim is made.

### 4.5 Why? — hypotheses tested, none supported

The brief's candidate mechanisms were measured rather than asserted. **Exploratory; no causal claim.**

- **"ECR discriminates where Y1 is nearly indifferent."** Not supported. Binning changed picks by
  the Y1 projection gap between the two players, the `<5 points` bin is the *best* bin in two cells
  (+29.7, +27.2) and the *worst* in the other two (+4.3, +0.3). Inconsistent in sign.
- **"ECR reaches players Y1 cannot see."** Ruled out by construction and confirmed: **0 of 727
  changed picks took a player carrying no ECR rank.** The treatment never reaches the unranked tail.
- **"ECR corrects positional projection bias."** Not testable here, by design — the permutation is
  within-position and holds every position's value multiset fixed. This is M7's axis, recorded as
  the follow-up in §1.1.
- **The K/DST correction is immaterial.** Permuting all six positions rather than D104's four moves
  the result by **+4.8 (target) / −12.3 (dynasty)**, both CIs spanning zero. D104's *stated reason*
  for excluding K/DST was factually wrong (§1.5); its *numbers* were not affected.

### 4.6 ECR alone — an independent benchmark, not a scoreboard

| format | objective | `ECR_ALONE − Y1` | 95% CI | seasons |
|---|---|---|---|---|
| target | season_long | **+31.6** | [−168.9, +232.1] | 4W/1L |
| target | weekly | −16.2 | [−132.3, +100.0] | 3W/2L |
| dynasty | season_long | **−60.5** | [−214.4, +93.4] | 1W/4L |
| dynasty | weekly | −82.0 | [−248.7, +84.6] | 1W/4L |

A consensus drafter and Alpha finish within a hundred points of each other, in both directions,
with every interval spanning zero. **Neither "Alpha beat ECR" nor "ECR beat Alpha" is supported by
this evidence**, and neither phrase is used.

**The result worth carrying forward from this arm is a different one.** `ECR_ALONE` and
`ECR_ALONE_NAIVE` differ by exactly one thing — whether the drafter must spend its last picks
filling mandatory starting slots:

| format | objective | `ECR_ALONE − ECR_ALONE_NAIVE` | 95% CI | t | seasons |
|---|---|---|---|---|---|
| target | season_long | **+241.1** | [+192.4, +289.8] | 13.75 | 5/5 |
| dynasty | season_long | **+215.3** | [+176.4, +254.2] | 15.35 | 5/5 |
| target | weekly | **+230.7** | [+178.3, +283.0] | 12.22 | 5/5 |
| dynasty | weekly | **+197.2** | [+156.9, +237.5] | 13.59 | 5/5 |

**This is the only effect in the phase that clears the 172–250 detection floor**, it clears it in
all four cells, and it is five to ten times any ECR information effect measured here. It is a
*roster-legality* effect, not an information effect. It is also a reminder about the benchmark
opponent: the consensus bot's documented lack of roster awareness (`docs/BENCHMARK_SPEC.md` §3)
is worth ~200 points a draft, so the choice between the two consensus variants is not cosmetic.

### 4.7 Power — what this experiment could and could not have detected

Realized MDE at 80% power, `(t₀.₀₂₅,₄ + t₀.₂₀,₄)·sd/√5`, for the four primary cells: **111.6,
139.4, 162.9, 429.5**. The observed effects are 21.4–88.9.

**So the experiment was not powered to resolve an effect of the size it actually observed.** Three
of four cells could have detected ~112–163 points; the observed effects are below that in every
case. This is outcome **H** alongside **B** and **D**, and it is stated rather than buried: *"not
statistically significant" here does not mean "ECR has no value."*

D108 reopening-criterion 1 already names the only lever that moves this: more independent season
clusters. Slots provably cannot (D88), seeds provably cannot (D92). With k = 5 and a per-season SD
of 67–346 points, no amount of within-season sampling reaches a 25–90 point effect.

### 4.8 Against the registered outcome list

| | outcome | supported? |
|---|---|---|
| A | Y1+ECR materially improves realized draft value | **No** — all four primaries below the floor |
| **B** | many picks change without improving value | **Yes, primarily** — 56.8% change, 36.7% better at roster level |
| C | ECR helps only in specific rounds/positions | partly — the phase split is sign-consistent, positions are not |
| **D** | ECR improves early decisions but hurts later ones | **Yes** — +24.1 / +16.6 / −8.7, late negative in 6/6 cells |
| E | ECR helps late but not early | **No** — the player-level view suggests it and the roster-level view refutes it |
| F | ECR-alone differs from Y1 but adding ECR does not help | partly — ECR-alone is a wash; adding ECR is positive but unresolved |
| G | ECR adds little or no useful incremental information | **not established** — the sign consistency and the ladder shape argue against it, and the power analysis forbids concluding it |
| **H** | the experiment is underpowered | **Yes** — MDE 112–430 vs effects of 21–89 |

### 4.9 What this phase does NOT license

- It does **not** show ECR should be added to production. Four unresolved positives are not a ship
  decision, and the registered stopping rule forbids a downstream run.
- It does **not** show ECR is useless. That is outcome G, and §4.7 explicitly rules out concluding
  it at this power.
- It does **not** overturn D104. D104 replicates here (§3.1). D111 measures a different arm.
- It does **not** say anything about projection *magnitudes*. Every treatment holds each position's
  value multiset fixed — D108 reopening-criterion 3's axis remains untested.
- It does **not** close the risk/uncertainty question, which was frozen throughout (§1.10).

---

## 5. The smallest next experiment

Not a fifth value base, not another ranking source, and not an ECR weight search.

> **Does enforcing roster feasibility earlier — rather than only at the end of the draft — carry
> the +197 to +241 point effect that is the one thing this phase resolved?**

The reasoning: every information-side lever measured across D97–D111 lands at 20–90 points, below
a floor of 172–250 that more seasons alone can lower. The mandatory-slot rule clears that floor
four times over, in both formats and under both objectives, at t ≈ 12–15. It is also *not* an
information question, so it is not blocked by the power ceiling that blocks everything else here:
the effect is large enough for k = 5 to see.

It is cheap — the rule already exists in `league/opportunity_cost.py::roster_aware_market_pick`,
and Y1's own `positional_feasibility_cap` is the natural comparison — and it needs no model, no
fitting and no new data.

**Recorded as a recommendation only. Not started.** Explicitly *not* recommended: promoting any
ladder rung, tuning w, a new projection model, ECR in production, or any use of 2026.

## 6. Reproduction

Artifacts are committed under `docs/d111_artifacts/` — the five run reports and every result JSON
except `d111_divergence.json` (2.9 MB; it regenerates deterministically from the command below).

```
uv run python scripts/research/d111_ecr_incremental.py --mode phase0         --out <dir>
uv run python scripts/research/d111_ecr_incremental.py --mode parity         --out <dir>
uv run python scripts/research/d111_ecr_incremental.py --mode value          --out <dir>
uv run python scripts/research/d111_ecr_incremental.py --mode divergence     --out <dir>
uv run python scripts/research/d111_ecr_incremental.py --mode counterfactual --out <dir>
uv run pytest tests/unit/test_d111_ecr_incremental.py
# board vintage: 63076e2e2bbfbbe5c29fb41265966ac1b8aaa180b3e89ee7742388fcc19d98ad
# ECR population (ro+do, Jul/Aug, 2021-2025):
#   c5cfbbeb17aabbf9b903ab55051984f735c4c03daca75a6328272144d378fb7f
```
