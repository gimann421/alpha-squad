# D102 — Defining the pick-level objective

> **SUPERSEDED IN TWO PLACES BY D103** (`docs/D103_PICK_LEVEL_OBJECTIVE.md`), which ran the
> experiment this report recommended and refuted two of its claims:
>
> 1. **§6a / §9's "under season-long scoring the endgame row is not measurable at all" is WRONG.**
>    Late-round regret measures 107.4 under season-long — 59% of the early figure, not a
>    degeneracy. `compute_league_starters` allocates the best ten of sixteen *by season total*, so
>    a late pick who turns out well does enter the lineup. What season-long cannot see is
>    **insurance** value (covering a starter's missing weeks), not late-pick value as such.
> 2. **§10's expectation of "a large and negative" interaction from Y1's uncertainty machinery is
>    WRONG.** With the rule held at Y1, the information effect is +795.3 / +717.0; the implied
>    decision-rule effect under oracle information is about −11 / −12 points. D97's reading of
>    `ORACLE − PROD` as information-shaped was close to right.
>
> The rest of this report — the definitions, the metric audit, the information boundary, and the
> instrumentation recommendations — stands, and D103 implemented all three of its §16 items.

**Verdict: DO NOT SHIP** (a definition phase has nothing to ship). Nothing was fitted, no model,
arm, or production path was touched.

**The headline finding is that the project already built the right instrument and then stopped
using it.** `evaluation/draft_oracle.py` (D86) measures exactly the quantity the north-star
objective names — how much value a pick created versus the best alternative available at that exact
moment — and it is rigorous about the information boundary. But it scores rollouts with the
**season-long** roster objective that D86's *own* Phase 1 proved prices the bench at exactly zero.
Late picks are bench picks. **So every pick-quality number this project has ever published is
structurally blind to the late third of the draft** — precisely the segment the north-star calls
out. Separately, D98–D101 spent four phases optimizing projection proxies (MAE → Spearman → top-6 →
AUC) without measuring a single draft pick, and D101 showed two of those proxies rank the same arms
in opposite orders.

---

## 1. Repository status

| check | result |
|---|---|
| working tree | clean |
| HEAD | `6d63a6a` (D101) on `d101-y-arm-identification` |
| `origin/main` | `277204f`; PR #19, #23 open, not merged |
| `models/` | `73b408e9bd12daecdd6a2a875e48735319b66aef` — Y1 baseline, **unchanged** |
| `league/` | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — Y1 baseline, **unchanged** |
| production code changed | **none** |

Read for this phase: `league/draft.py`, `replacement.py`, `opportunity_cost.py`, `roster.py`;
`evaluation/draft_oracle.py`, `weekly_objective.py`, `objective_candidates.py`,
`decision_counterfactuals.py`, `pick_attribution.py`, `draft_forensics.py`, `draft_simulation.py`;
and the D85–D101 decision records.

## 2. The north-star objective, restated precisely

> At every individual draft pick, maximize the quality of the choice made — early, middle and late.

This is a **pick-level, state-conditional** objective. It is not a roster objective, and it is not
any projection-accuracy metric. Three consequences follow immediately and govern everything below:

1. A pick's value is only defined **relative to a continuation policy**. "Was this the best pick?"
   is meaningless without saying what happens afterwards.
2. A pick's value is only defined **relative to a roster-value function** `U(roster)`. If `U` is
   wrong, every pick score built on it is wrong in the same direction.
3. Pick quality is **conditional on state**, so it cannot be recovered from any season-level
   aggregate.

## 3. What makes a pick good — from first principles

At pick `p` the state is `S_p = (R_p, A_p, L, I_p)`: the roster already selected, the players still
available, the league configuration, and the information available at that moment. Selecting
candidate `c` yields

    V_π(c | S_p) = E[ U(final roster) | take c at S_p, then play by policy π ]

and `c` is better than `c'` exactly when `V_π(c) > V_π(c')`. The **quality of the pick actually
made** is its shortfall against the best available option:

    regret(p) = max_{c ∈ A_p} V_π(c | S_p) − V_π(chosen | S_p)

This is the definition the rest of the report builds on. It has the properties the objective needs:
it is per-pick, conditions on roster and availability, and is zero when the engine picked the best
available option — regardless of whether that option happened to score a lot.

## 4. Ex ante, ex post, counterfactual — and which is primary

| | question | role |
|---|---|---|
| **A. ex ante decision quality** | was this the best decision on the information available? | **what we want to improve** — but not directly observable, because it requires knowing the true conditional expectation |
| **B. ex post realized value** | how well did the player actually do? | **not a decision metric.** Dominated by luck |
| **C. counterfactual pick value** | how much better/worse would the roster be under another available player? | **the primary evaluation target** |

**C is primary, and A is the thing C is used to estimate.** B is rejected as a target on measured
grounds, not stylistic ones: D86 found `Spearman(Alpha's score, final roster value) = −0.033` across
320 real pick states, and that **~90% of measured regret is the realized-points gap** (104.1 of
116.2) — i.e. the oracle's winning candidate usually just scored more, which no decision rule could
have known. A metric dominated ~90% by luck cannot steer a decision rule.

The resolution that makes C usable is the information boundary in §5. C is computed *ex post* — it
must be, outcomes are how we score — but it adjudicates an *ex ante* decision, because the policy
that generated the decision never saw an outcome.

## 5. The information boundary

Stated as a rule, because everything depends on it:

> **Realized outcomes may be used to SCORE a decision. They may never be used to GENERATE the
> decision being scored, nor to generate the continuation that scores it.**

`draft_oracle.py` already implements this correctly and pins it structurally rather than by
convention. Outcomes enter in exactly one place — scoring a finished roster. They do not enter the
rollout policy (the shipped engine reading Y1 projections), the opponent model (`roster_aware_
market_pick`, preseason ECR only), and `assert_no_realized_inputs_in_policy` enforces the first two
by signature inspection.

One deliberate and correct exception: the **candidate slate** includes the realized-points top-N.
That is an evaluation-side input, not a policy input. Without it the oracle could only choose among
players Alpha already liked, which would bias measured regret toward zero. The module says so
explicitly, and it is the reason it can never be used in production.

**The boundary is therefore already solved. Nothing in this report proposes changing it.**

## 6. The counterfactual best-pick definition — it already exists

**Yes.** `evaluation/draft_oracle.py` (D86) implements it. Documented exactly:

- `V(c)` = **realized starter points of the final roster** if `c` is taken now and the rest of the
  draft is played by `rollout_policy` (default `SHIPPED_TIER = "L0"`, the shipped engine).
- oracle pick = `argmax_c V(c)`; **`regret` = `max_c V(c) − V(alpha's pick)`**.
- slate = union of Alpha's top-10, the realized-points top-10, and the projection top-5,
  deterministic with a `player_id` tie-break.
- also reports the **rank correlation** between Alpha's score and `V(c)` across the slate.

This is a **one-step oracle under a fixed continuation policy**, which the module correctly argues
is the right diagnostic: it isolates one decision while holding everything downstream constant, and
it is a conservative *lower* bound on the value of a better objective. A full dynamic program over
a 160-pick game on an ~840-player board is not computable and is also not the right question,
because Alpha will not play optimally afterwards either.

### Three defects that must be fixed before it can serve the north-star

**(a) It is scored with the wrong roster-value function — and this is disqualifying for late
picks.** `_score_roster` calls `compute_league_starters` on `_actual_points_for`, which returns
`total_fantasy_points_ppr` — **season totals, one lineup allocation**. D86's own Phase 1 proved this
objective cannot see a bye, cannot see an injury, and therefore **prices the bench at exactly
zero**, while measuring that **17.8% of realized points come from players it never starts** and that
a bench player enters the lineup in **16.2 of 17 weeks**.

Rounds 13–16 are bench picks. Under season-long scoring a bench pick contributes zero to `V(c)` no
matter who it is, so `regret` at those picks is near-degenerate by construction. **The project has
never had a valid measurement of late-pick quality.** The fix requires no new data and no new idea:
`weekly_objective.weekly_lineup_points_no_foresight` already exists, is tested, and is the correct
`U`. The two functions are interchangeable at one call site.

**(b) The rollout policy's production parity is true today but not pinned.** The module states that
"`L0`/`Q0`/`Z0` are asserted byte-identical to `recommend_draft_pick` by existing tests". No such
test exists. `test_l0_is_the_shipped_engine` compares L0 only to **Q0 and Z0 — sibling replicas in
the same harness** — so a drift common to all three passes silently; and the only test that touches
production, `test_tier_h_matches_a_direct_recommend_draft_pick_call`, pins tier **H** on the
**first pick** of a synthetic 5-round league. I checked the claim empirically rather than assuming
either way: **L0 and H agree on 240 of 240 real pick states** (§17.1). So the D86 lineage is sound
as of today; what is missing is the guarantee, not the property. That is a cheap test to add, not a
defect to correct.

**(c) It is a lower bound, by design.** The continuation is the shipped (imperfect) policy, so a
better objective would also improve the continuation. The module states this. It is the
conservative direction and should be kept.

### The two weaker counterfactuals, and why they are not the primary

- **`pick_attribution.py`** — replays Alpha's draft and asks what the consensus *rule* would have
  taken from the same pool, then swaps that one pick into the final roster. Honest and cheap, but
  its own docstring says it "does not model how taking a different player would have changed which
  players were available at later picks". It also compares against *consensus*, not against *best
  available*. **Diagnostic, not primary.**
- **`decision_counterfactuals.py`** — component ablation at a pick state (which term drove the
  recommendation). Mechanistic, not outcome-based. **Diagnostic, and valuable for §13's attribution.**

## 7. Marginal value versus absolute player value

The user's concern — that `projection(A) − projection(B)` is the wrong value for a pick when B
would survive to the next turn — is **already the engine's design**, not a gap. From
`league/draft.py`:

    score = (marginal_starter_value + 1.0·VORP_draft_aware + positional_opportunity_cost)
            × roster_fit × confidence × survival × [0.1 if past the usable cap]

- `marginal_starter_value` prices a candidate against **what he would displace in the current
  lineup** — so a body at a saturated position is worth what it adds, not what it scores.
- `VORP_draft_aware` (D67) draws replacement at **the best player at that position who will still
  be undrafted when the draft ends**, so it moves with the board rather than being fixed at pick 1.
- `positional_opportunity_cost` (D55) prices **the drop at that position expected by our next
  turn** — this is exactly the "would B still be there at pick 9?" term. D97 measured it as
  directionally calibrated (corr 0.73–0.88) while understating magnitude 20–65%.
- `survival` prices the individual player's chance of lasting to the next turn.

So the correct pick objective is marginal, the engine already implements it, and **the evaluation
must match**. The rollout oracle does: because the continuation keeps drafting, a candidate who
would have survived to the next turn does not earn the engine a penalty for passing on him — the
rollout may simply take him later. This is precisely the property `pick_attribution.py`'s
single-pick swap lacks, and it is the strongest reason the rollout oracle is the primary.

## 8. Roster-context requirements

Pick evaluation **must** condition on roster state, remaining slots, positional scarcity,
replacement level, remaining picks, expected availability, and lineup constraints. The repository
supplies the proof rather than the assertion: `marginal_starter_value` on an **empty** roster is
mathematically identical to the candidate's own projection, i.e. pure best-player-available by raw
points — and in a 1-QB league raw points favour quarterbacks, which is exactly the pathology that
made the pre-D63 engine take a QB in round 2 in 68% of drafts and reach its first RB at round 5.24.

An evaluation metric that does not condition on roster state reproduces that pathology in the
*ruler*: it would reward selecting whoever eventually scored most, which is the failure mode §7 of
the brief warns against. The rollout oracle conditions on all of it by construction, because `V(c)`
is the value of a **finished roster** reached from the actual state.

## 9. Early / middle / late evaluation

**Never collapse to one average.** Segmentation justified by the repository's actual structure —
`roster_size = 16`, 10 starters + 6 bench (D58):

| segment | rounds | what the pick is for | what dominates (D97 §4) |
|---|---|---|---|
| **opening** | 1–4 | the starter core; elite value | `msv` owns the opening (73/160 early) |
| **build** | 5–8 | completing the lineup; scarcity, timing | mixed |
| **depth** | 9–12 | flex and depth; mandatory-slot risk appears | `daVORP` rising |
| **endgame** | 13–16 | bench and marginal value | `daVORP` owns it (138/160 late); `capacity` binds only late (0 early, **52 late**) |

Two measured facts make segmentation mandatory rather than stylistic. D86 found the spread of
`V(c)` across the slate decays from **343.7 in round 1 to 113.0 in round 16** — so an unweighted
average of regret is dominated by the opening and would hide an endgame regression entirely. And
D97 found the components' influence is strongly phase-dependent, so an intervention can help one
phase while hurting another with no visible change in the aggregate.

Report each segment separately **and** an all-picks aggregate, never the aggregate alone. This is
what detects the four patterns the brief names (improves early/hurts late, etc.).

**Caveat that cannot be skipped:** under the current season-long scoring the **endgame row is not
measurable at all** (§6a). Segmenting the existing instrument today would produce a table with a
structurally empty right-hand column.

## 10. Oracle-gap interpretation

D97's headline was `ORACLE − PROD = +784.6` in the target format, read as "projection headroom".
**That reading is not supported by the design of the experiment, and the phase's three arms cannot
separate the quantities.** D97's arms:

| arm | information | decision rule |
|---|---|---|
| `NAIVE` | Y1 projections | classic VBD |
| `PROD` | Y1 projections | **Y1** |
| `ORACLE` | **realized (perfect)** | classic VBD |

`ORACLE − NAIVE = +998.4` is a clean information effect — same rule, different numbers. `PROD −
NAIVE = +213.8` is a clean rule effect — same numbers, different rule. But **`ORACLE − PROD` is
neither**: the two arms differ in information *and* in decision rule simultaneously. It is the
arithmetic residual `998.4 − 213.8`, and it answers only "by how much would a perfect-information
VBD drafter beat Y1?"

The missing cell is the fourth corner of the 2×2:

| | NAIVE rule | Y1 rule |
|---|---|---|
| Y1 projections | `NAIVE` ✅ | `PROD` ✅ |
| realized (perfect) | `ORACLE` ✅ | **`ORACLE_Y1` — never run** |

With `ORACLE_Y1` the decomposition becomes identified:

- **information value, rule held at Y1** = `ORACLE_Y1 − PROD`
- **rule value, information held perfect** = `ORACLE_Y1 − ORACLE`
- **interaction** = the difference between the two rule effects

There is a specific reason to expect the interaction to be large and negative, which makes the
current reading actively misleading: **most of Y1's apparatus is uncertainty management.**
`survival`, `confidence` and `positional_opportunity_cost` all exist to hedge against not knowing
what happens next. Under perfect information there is nothing to hedge, so `ORACLE_Y1` could
plausibly be *worse* than `ORACLE` — in which case part of the +784.6 is "Y1's hedging is
unnecessary when you already know the answer", not "Y1's projections are bad".

**Two further limits on the +784.6, both of which matter more than the decomposition:**

1. It is the value of **perfect** information, which is an upper bound on nothing achievable. D100
   subsequently measured the achievable slice of the identification gap at **+0.80 of 6**, and found
   **45% of the gap is information not present in M6's features in any combination**. The achievable
   share of the 784.6 has never been estimated, in four phases of work premised on it.
2. `ORACLE` is a whole-draft hindsight policy, so it is not a pick-level quantity at all. **D86's
   pick-level instrument gives the decision-shaped number directly**: the structural residual —
   picks where the oracle's player scored **no more** and still produced a better roster — was
   **16 of 320 (5%)**, worth **~90 points per draft as an upper bound**, against a minimum
   detectable effect of ~128. Those two numbers are not in conflict with D97; they are the
   pick-level reading of the same fact.

## 11. Existing metric audit

### 11.1 A parity check on the rollout policy

§6b noted that L0's production parity is asserted but not pinned. It was checked (§17.1): **240 of
240 real pick states agree**, so every D86-lineage regret number does describe the production
policy. The audit below therefore treats the oracle's rollout as sound and its *scoring function*
as the defect.

### 11.2 Classification

| metric | where | class | why |
|---|---|---|---|
| **pick-level regret under fixed continuation** | `draft_oracle.py` | **PRIMARY CANDIDATE** | the only existing quantity that is per-pick, roster-conditional, counterfactual, and leakage-safe — *conditional on fixing the scoring function* |
| **rank correlation of score vs `V(c)`** | `draft_oracle.py` | **PRIMARY CANDIDATE (companion)** | scale-free check that the objective *orders* candidates the way outcomes do; D86 measured −0.033 |
| weekly no-foresight roster points | `weekly_objective.py` | **PRIMARY CANDIDATE (as `U`)** | the correct roster-value function; sees byes, injuries, and the bench |
| season-long starter points | `draft_simulation.py` | **MISALIGNED as `U`** | prices the bench at 0; 17.8% of realized points invisible. Retain only for continuity with pre-D86 numbers |
| final roster points (total, incl. bench) | `draft_simulation.py` | SECONDARY | ignores lineup legality; a roster of 16 QBs scores well |
| bench points | `weekly_objective.py::bench_contribution` | DIAGNOSTIC | the quantity that exposes defect (a) |
| single-pick consensus swap | `pick_attribution.py` | DIAGNOSTIC | no downstream availability modelling, and vs consensus not vs best available |
| component ablation | `decision_counterfactuals.py` | DIAGNOSTIC | mechanistic attribution for §13 |
| `daVORP`, `msv`, replacement level, opportunity cost, survival, roster fit, capacity | `league/` | **INPUTS, not metrics** | they are terms of the objective under test; scoring the engine with its own terms is circular |
| MAE, RMSE | `projection_specification.py` | DIAGNOSTIC | pool-wide accuracy over ~150 players; the product consumes ~20 |
| Spearman | same | DIAGNOSTIC | whole-pool ordering; D101 showed it disagrees with tail identification |
| AUC | D100/D101 harnesses | DIAGNOSTIC | whole-pool, tail-insensitive; D101 ranked Y3 first on AUC and Y1 first on hit rate |
| top-6 identification | D100/D101 | DIAGNOSTIC | a proxy for a proxy; never shown monotone in pick quality |
| top-12 / top-decile bias | `projection_specification.py` G6 | **UNRESOLVED** | prose and code are different statistics (D101 §5.4); decides Y2/Y3 |
| positional hit rates | D97 §3 | DIAGNOSTIC | useful for attribution, not a target |
| oracle gap (`ORACLE − PROD`) | D97 | **UNRESOLVED** | not identified without `ORACLE_Y1` (§10) |
| draft pick differences (first-QB round, K count) | D86/D97 | DIAGNOSTIC | behavioural tells, not value |

**No metric is promoted merely because it exists.** Every projection metric in this table is
classified DIAGNOSTIC, and that is the substantive result of the audit.

## 12. Proposed primary pick-quality metric

> **`regret_weekly(p)` = `max_{c ∈ slate(p)} V(c) − V(chosen)`, where `V(c)` is the realized
> WEEKLY, NO-FORESIGHT lineup points of the final roster obtained by taking `c` at pick `p` and
> playing the remainder with the shipped engine — reported per draft-phase segment and in
> aggregate, alongside `Spearman(engine score, V(c))` on the slate.**

This is D86's instrument with one substitution: `U` becomes the weekly no-foresight objective
instead of the season-long one. Everything else — the slate, the tie-breaks, the leakage guard, the
fixed-continuation argument — is kept unchanged because it is already right.

**Can the project measure pick optimality directly?** Honest answer: **almost, but not yet, and not
for the segment that matters most.** The instrument shape exists and is sound. What does not yet
exist is (i) that instrument running on the correct `U`, (ii) a pinned guarantee that the rollout
policy is production, and (iii) the `ORACLE_Y1` cell for attribution. All three are small.

**What this metric still cannot do, stated rather than implied:**

- It is a **lower bound** (fixed imperfect continuation).
- It inherits the ~90%-luck signal-to-noise D86 measured. It must be reported *decomposed* (§13),
  never as a single headline number.
- With 5 seasons × 10 slots it faces the same hard-capped cluster count as every other draft
  measurement here; D97's MDE of ~172–250 points applies to draft-level contrasts. Per-pick regret
  has ~50× more observations than a roster total, but they are **not independent** — picks within a
  draft share a board and a roster path. Any inference must cluster on the draft, not the pick.

## 13. Projection versus decision attribution

The four categories are separable from the existing oracle's own outputs, with these signatures:

| category | signature in the oracle output | status |
|---|---|---|
| **D. evaluation artifact** (luck) | the oracle's player **scored more**; the engine could not have known | **measured: ~90%** of regret (104.1 of 116.2) |
| **B. bad decision logic** | the oracle's player scored **no more** and still produced a better roster — the objective mis-ordered candidates it valued correctly | **measured: 16/320 (5%)**, ~90 pts/draft upper bound |
| **A. bad information** | the oracle's player was identifiable from information available at the time, and Alpha's projection missed him | **not separable today** — needs `ORACLE_Y1` |
| **C. unavoidable uncertainty** | `V(c)` is flat across the slate; several picks defensible | computable from the existing slate spread; not yet reported |

**The rule this implies, and it is the phase's main methodological output:** never conclude "fix
projections" from the existence of projection error, and never conclude "fix the decision engine"
from a pick that underperformed. Both inferences are category errors that this taxonomy makes
mechanical to avoid. On current evidence **D dominates, B is small and below the measurement floor,
and A is unquantified** — and A being unquantified is exactly what D98–D101 assumed away.

## 14. Challenging the D97–D101 direction (mandatory)

**Are D97–D101 pointing at the correct next layer? Partly — the diagnosis holds, the prescription
does not, and the execution drifted far from both.**

**D97's diagnosis is corroborated and I do not overturn it.** "The decision layer is not the binding
constraint" is supported *independently* by D86's pick-level instrument, which put the
decision-shaped residual at ~90 points per draft against a ~128-point MDE. Two different instruments
agreeing is real evidence. D97's component audit (opportunity cost calibrated at corr 0.73–0.88;
`capacity` binding only late; `daVORP` owning the endgame) is sound work.

**But four specific challenges stand:**

1. **`ORACLE − PROD = +784.6` does not measure projection headroom.** It confounds information with
   decision rule (§10). The number D97 was entitled to is `ORACLE − NAIVE = +998.4`; the residual
   against PROD is not identified, and the missing arm is cheap.
2. **"Resolvable" was conflated with "achievable".** D97 argued the projection gap is 3–4× the MDE
   and therefore the right target. That establishes the *bound* is detectable, not that any
   *reachable* improvement is. D100 later bounded the reachable part of the identification gap at
   +0.80 of 6 with 45% of it absent from the data — which, had it come first, would have changed
   D97's recommendation.
3. **D98–D101 never measured a draft pick.** Four consecutive phases optimized MAE, Spearman, AUC
   and top-6 identification. None of these has ever been shown to be monotone in pick quality, and
   D101 proved they are not even monotone in *each other*: AUC and Spearman rank Y3 first, top-6
   hit rate ranks Y1 first. **D100's emphasis on top-6 identification is a proxy for a proxy** —
   D97 proposed it because capture rate correlated with the positional reallocation `ORACLE` made,
   which is an association observed in one whole-draft arm, never a pick-level measurement.
4. **D86 — the one phase that used the pick-level instrument — explicitly recommended against this
   direction**, listing "projection work (D79–D83)" under *Not recommended next*. D97 reversed that
   without re-running the pick-level instrument, and no phase since has run it either.

**Does the D97–D101 body of work establish that improving projections will improve individual draft
decisions? No.** It establishes that *perfect* projections would produce a different and better
draft. That is not the same claim, and the gap between them is where the last four phases were
spent.

**What I am *not* claiming:** that the decision layer is where the value is. D86 and D97 agree it is
not, and I have no evidence to overturn that. The correct conclusion is narrower and more
uncomfortable: **on the metric that actually encodes the product objective, the project does not
currently know where the value is, because that metric has never been run on a valid roster-value
function.**

## 15. Recommended research hierarchy

Confirmed as the user proposed, with one amendment and one demotion:

1. **Ultimate objective — maximize the quality of every individual pick.** Measured by
   `regret_weekly(p)`, **reported by draft phase**, decomposed by the §13 attribution taxonomy.
   *(Amendment: the phase segmentation and the attribution decomposition are part of the objective,
   not presentation. An undecomposed regret number is ~90% luck and will mislead.)*
2. **Secondary — the resulting roster**, scored weekly and no-foresight. Validation, never the
   optimization target: one pick moves it by ~2.6% and `Spearman(score, roster value) = −0.033`.
3. **Information quality — projections should help the engine identify valuable players.** Demoted
   relative to the current research direction, and **conditional**: a projection change earns
   attention when it moves `regret_weekly`, not when it moves MAE, Spearman, AUC or top-6.
4. **Diagnostic metrics — MAE, RMSE, Spearman, AUC, top-6, top-decile bias.** Useful for explaining
   *why* a pick metric moved. **None is a decision criterion.**

The user's prior — pick quality primary, roster quality downstream validation — is **confirmed**,
and §5's evidence is what confirms it rather than taste.

## 16. Smallest next experiment / instrumentation

Three small, strictly diagnostic changes, in dependency order. None fits a model, adds a feature,
changes an arm, or touches `models/`, `league/`, or production.

**(1) Pin the rollout policy to production.** Add a test asserting tier `L0` picks identically to
tier `H` across pick states — the assertion `test_l0_is_the_shipped_engine` claims and does not
make. §17.1 confirms the property holds today (240/240), so this is cheap insurance on every
D86-lineage number, not a repair.

**(2) Re-score the existing oracle on the correct `U`.** Give `draft_oracle._score_roster` the
weekly no-foresight objective that `weekly_objective.py` already provides, as a parameter with the
season-long function retained as the default so every published D86 number stays reproducible. Then
re-run the existing 320 pick states and report `regret` **by draft-phase segment**. This is the
first valid measurement of late-pick quality the project will have. Both functions exist and are
tested; no new data, no fitting.

**(3) Add the missing oracle cell.** Construct `ORACLE_Y1` — realized points substituted into
`SeasonStatic.projections`, scored by the **production** rule — to identify the §10 decomposition.
The mechanism already exists: the X/Y/L tier family takes substituted projections with the shipped
replacement rule unchanged, which is exactly what this needs.

Only after (1)–(3) does the question "projections or decision logic?" have an identified answer.
Until then, the honest statement is that it is **unresolved**, and four phases have been spent
acting as though it were not.

**Explicitly not recommended:** another value base (nine have failed), a Y4, a lookahead optimizer,
further projection-proxy optimization, or any use of 2026.

## 17. Validation performed, and decision

### 17.1 Tier L0 versus production

The one validation this phase ran — permitted as a check on whether an *existing* metric is valid,
not as a new experiment. Read-only, no fitting, no new arm: it replays production (tier `H`, the
real `recommend_draft_pick`) over 2021–2025 × slots {1, 5, 10} × 16 rounds and, at each state,
asks tier `L0` — the rollout policy every D86 regret number depends on — for its pick from the
identical pool, roster and pick numbers.

> **L0 vs H over 240 real pick states: agree 240, disagree 0.**

So `draft_oracle.py`'s rollout **is** the production policy, and the D86 lineage is not
contaminated. The claim in its docstring is true; it is simply not defended by any test, which is
why §16(1) proposes adding one. This is a positive result and it narrows the phase's finding: the
oracle's *policy* is sound, and its *scoring function* is the thing that is wrong.

### 17.2 Decision

**DO NOT SHIP.** A definition phase produces no shippable artifact, and none was produced.
`models/` and `league/` are byte-identical to the Y1 baseline, no production code changed, no model
was fitted, no arm was created or modified, no draft simulation was run, no 2026 data was used, no
PR was created and nothing was merged.
