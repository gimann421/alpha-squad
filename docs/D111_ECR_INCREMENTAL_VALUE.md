# D111 — Does ECR add incremental information that improves Alpha's actual draft decisions?

> **§1 is the pre-registration. It was committed before any treatment arm was run.** Results begin
> at §4. Nothing in §1–§3 was edited after a treatment number was seen; corrections, if any, are
> appended as marked notes rather than made silently.

**Status: PRE-REGISTRATION COMMITTED — results pending.**

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
| **P1** | tier `L0` picks identically to tier `H` (a direct pass-through to production's `recommend_draft_pick`) at every pick state of every registered draft — D107's 640/640 check, re-run on this vintage. This is what makes the control production-equivalent | *pending* |
| **P2** | every arm at w = 0 is **byte-identical** to Y1 — the projection dict, the VORP dict and the chosen player, at every pick state. An arm differing from the control by anything other than the pre-registered ECR input fails here | *pending* |
| **P3** | every treatment preserves each position's value multiset exactly (`SubstitutionError` otherwise), so replacement levels, scarcity and consumption demand are unchanged | *pending* |
| **P4** | pool parity: the candidate universe is identical in every arm | *pending* |
| **P5** | the ECR board hash of §2.1 reproduces, and the vintage is recorded with every artifact | *pending* |

---

## 4. Results

*Pending — this section is written only after §1–§3 are committed.*

---

## 5. Reproduction

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
