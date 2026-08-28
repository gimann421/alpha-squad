# Draft strategy: next-phase implementation plan

What to change, in what order, measured how, with what pre-registered decision rule — and what
not to change.

Evidence base: `docs/DRAFT_STRATEGY_FORENSIC_ANALYSIS.md`. Objectives:
`docs/DRAFT_OBJECTIVE_MODES.md`. Benchmark mechanics: `docs/BENCHMARK_SPEC.md`.

---

## 0. The governing principle for this phase

**Nothing may be tuned against the current benchmark, because the current benchmark rewards
the wrong thing.** Its consensus opponent forfeits its K and DEF starting slots, which is worth
+245.3 starter points — more than the entire margin any engine change has ever produced. Every
engine decision made against it is contaminated, including D60's.

So the sequence is: **fix the measurement first, re-establish the true baseline, then and only
then change the engine.** Stages 1 and 2 must complete before Stage 3 begins.

---

## Stage 1 — Fix the measurement (no engine change)

### 1.1 Make the consensus opponent roster-aware

`evaluation/draft_simulation.py::_market_consensus_pick` and the opponent field.

Change: a consensus drafter fills a still-empty **mandatory dedicated starting slot** in its
final rounds when the number of picks remaining equals the number of unfilled mandatory slots.
Within the position it still takes best-available by ECR. No hindsight, no projection access.

Derive "mandatory dedicated slot" from `league.dedicated_slots()` — never a hardcoded
`{"K","DEF"}`. In a league with no kicker slot this changes nothing, which is the correctness
test.

Rationale, stated plainly: an opponent that cannot field a legal lineup is not a benchmark. The
existing behavior is not a conservative choice, it is a broken one, and it flatters Alpha.

**Preserve the historical record.** Do not silently restate published numbers. Report both
opponents side by side in `reports/draft_simulation.md` for at least one release —
`market_consensus` (as published through D60) and `market_consensus_roster_aware` — with a
banner naming which one the headline claim uses. Every pre-existing number keeps its meaning
and gains a label, exactly as D56 handled the `rsf`→`ro` correction.

### 1.2 Reconcile the forensic feasibility cap with production

`evaluation/draft_forensics.py::_feasibility_cap` is the pre-D58 flex-blind formula; production
calls `league/roster.py::positional_feasibility_cap`. Delete the forensic copy and call the
production function.

This invalidates the absolute M-tier numbers (M0 1894.2 … M3 2003.8). They must be re-run, not
reinterpreted. Add a test asserting the forensic harness and production return the same cap for
every position in every shipped league config, so they cannot drift again.

### 1.3 Fix `pick_attribution.py` to measure the shipped engine

Pass `roster_player_ids=my_roster` to `recommend_draft_pick` (the list is already maintained on
line 164 and used for scoring; it is simply not passed to the engine). One argument.

Then re-run the attribution. `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §7 currently describes the
D55 VORP engine while claiming to describe the shipped D60 engine; the RB-residual finding must
be re-derived before it can be cited about the shipped engine.

### 1.4 Add opponent feasibility to the benchmark report

Report, for every strategy including the opponent field, the count of unfilled mandatory
starting slots. A forfeited slot must be visible in the report rather than silently scoring
zero. This is the specific reporting gap that let §1's artifact survive four documented phases.

### 1.5 Scope `next_pick_survival_probability` by `page_type`

`league/draft.py` filters `market_snapshot` on `ecr_type` alone; `ecr_type='ro'` mixes
`redraft-overall` with the separately-ranked `redraft-idp` board (the whole reason D56 exists).
Route it through `_preseason_overall_market`'s scoping, matching every other market consumer.
Latent rather than demonstrated-harmful, but it is a one-line correctness fix in the same area.

### 1.6 Correct the documentation errors

- `docs/DECISIONS.md` D60 and `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §8: total roster points
  **2775.9 → 2455.0**.
- `docs/PROJECT_STATE.md` status header and milestone table stop at M15; extend through M19.
- M19 summary "+109.6" vs D60's "+109.7".
- Reopen `docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0 with the §1 finding. Its acceptance
  criterion was declared met on the contaminated benchmark.

**Stage 1 exit criterion:** a re-run official benchmark against the fair opponent, with both
opponents reported, determinism verified across two processes, and the true current baseline
recorded. Expected, from this phase's measurement: **Alpha ≈ −48 vs fair consensus, 25/50.**
If the re-run disagrees materially with that, investigate the disagreement before proceeding.

---

## Stage 2 — Re-establish the baseline and re-run the ablation honestly

With Stage 1 landed, re-run the M-tier ablation under production's real caps and the fair
opponent. This answers a question that is currently open: **does MSV actually beat VORP when
the comparison is not distorted?**

Report M0–M3 again. Treat the previous M-tier table as superseded, not merely refined.

---

## Stage 3 — The engine change, chosen by pre-registered ablation

### The hypothesis

VORP and MSV each fix what the other breaks:

- **VORP** encodes league-wide positional scarcity (correctly refuses an early QB in a 1-QB
  league) but prices a bench K/DST above replacement, so it hoards them (M0: 3.78 K/draft).
- **MSV** encodes lineup saturation (a second kicker is worth exactly zero) but on an empty
  roster equals the raw projection, so it reaches for QBs (4–5 of top-5 become QBs).

D60 chose one and discarded the other. The candidate change keeps both.

### Candidate value bases (tiers for the next ablation)

| tier | value base | rationale |
|---|---|---|
| **N0** | shipped D60: `msv` | control |
| **N1** | `vorp` | the D55 value base, as a second reference point |
| **N2** | `min(vorp, msv)` | scarcity early (MSV ≥ VORP on an empty roster, so min = VORP), saturation late (MSV → 0, so min → 0). Verified directionally on real 2023 data: empty-roster top-5 becomes WR/WR/TE/WR/WR, and a bench kicker's value goes VORP +17.2 → min 0.0 |
| **N3** | **marginal starter value over replacement**: `best_lineup(roster + candidate) − best_lineup(roster + replacement_player_at_that_position)` | the principled unification. Reduces to VORP on an empty roster and to 0 at a saturated position, by construction rather than by clamping. Most likely to be right; also the most code |
| **N4** | `msv + w·vorp`, w pre-registered | the additive blend, closest to the M1 tier that scored 1987.2 |

N2 and N3 are the front-runners. N2 is a one-line change to `league/draft.py`; N3 needs a new
function in `league/replacement.py` alongside the existing `marginal_starter_value`.

### Known failure mode to measure, not assume

In the late rounds every startable slot is full, so MSV → 0 for nearly every candidate. Under
N0 and N2 the value base collapses toward zero and picks are decided by the opportunity-cost
term and tie-breaks. N3 has the same property. This is arguably *correct* under Mode A (a bench
player genuinely contributes no starter points) and *wrong* under Mode B (bench depth is real
insurance). The ablation must report late-round behavior explicitly rather than only the
season total — it is the clearest place where the two modes should diverge.

### Also fix the scale mismatch

`opportunity_cost` is VORP-denominated and is added to whatever the value base is. Under D60
that base is MSV — different units. Whichever tier wins, the opportunity-cost term must be
expressed in the same currency as the value base, or measured with it switched off. This is
the opportunity-cost re-ablation that has been open since D60 and it belongs in this stage,
as an explicit `--no-opportunity-cost` arm rather than an assumption.

### PRE-REGISTERED DECISION RULE — commit to source before any run

Copy this into `evaluation/draft_forensics.py` as constants before executing anything:

- **Control:** N0 (the shipped D60 formula), run under production's real caps against the fair
  opponent.
- **Primary metric:** mean realized starter points against the **fair** opponent.
- **Gate 1:** no starting-requirement position zeroed at a higher rate than the control.
- **Gate 2:** `n_infeasible_rosters` no higher than the control (control is 0, so: 0).
- **Gate 3 (new, from this phase's findings):** mean starter points must not be worse than the
  control in more than **1 of the 5 seasons**. This blocks a tier that wins the pooled mean on
  one big season — the failure mode the current evidence base is most exposed to.
- **Gate 4 (new):** the winning tier must not draft any position at a mean round earlier than
  the control by more than 2 rounds without a measured justification. This catches the D60
  K/DST timing regression, which no existing gate would have caught.
- **Tie-break:** fewer mechanisms; then lower starter-points variance.
- **Ship only if** a tier strictly beats the control on the primary metric with all four gates
  passing.

### Robustness requirement (new for this phase)

Report **leave-one-season-out**: for each of the 5 seasons, the winning tier's margin computed
with that season excluded. A mechanism whose advantage disappears when any single season is
removed is not shipped, regardless of the pooled mean. This is the concrete guard against
overfitting to 2021–2025 that the directive asks for.

---

## Stage 4 — Mode A / Mode B split

Only after Stage 3 has a validated value base.

1. Add an explicit mode parameter to `recommend_draft_pick` with a documented default.
2. Mode A: legality-floor caps only; drop the proportional bench-share shaping from
   `positional_feasibility_cap` in this mode and measure whether it was helping.
3. Mode B: add the availability-adjusted objective. Build the games-missed distributions from
   `player_week_stats` (2015–2025, already ingested) — real measured availability, not an
   assumed injury rate.
4. Report the full tradeoff table from `docs/DRAFT_OBJECTIVE_MODES.md` §3.
5. Choose the user-facing default **from the measurement**. If Mode B does not earn it, say so
   and ship Mode A as default.

---

## Stage 5 — Close the production/benchmark gap

Three of four production entry points run the un-benchmarked VORP path
(`docs/DRAFT_STRATEGY_FORENSIC_ANALYSIS.md` §6). Whatever wins Stage 3 must actually reach
users:

- `cli.py`: track and pass the team's own drafted player ids.
- `agents/registry.py`: accept player ids in the task params, not only position counts.
- `web/src/components/DraftView.tsx`: track *my team's* picks separately from league-wide
  `draftedIds`, then pass them. This is the real fix for the deliberate omission documented in
  D60 — the omission was correct given the data available; the fix is to make the right data
  available.
- Add a test asserting every production call site supplies the arguments the benchmarked
  configuration requires, so this cannot silently regress.

---

## Explicitly NOT to be pursued

Named with reasons, per the directive.

| approach | why not |
|---|---|
| **Multi-pick lookahead / DP / Monte Carlo draft simulation** | The evidence does not show the simple architecture failing. It shows one *term* (the value base) was replaced with a term that discards scarcity, plus a broken benchmark. Fix those first. Escalating now would bury a one-line bug under a new subsystem and make attribution impossible. |
| **Learned draft policy** | 50 drafts × 5 seasons is nowhere near enough to fit a policy without memorizing the test set. It would also destroy the explainability the product's `reasons` strings provide. |
| **Opponent modeling beyond the ECR replay** | We have no real draft logs and no ADP (D16/D17). Any opponent model would be fitted to the same ECR board the opponent already uses — circular. |
| **Adding `positional_scarcity()` to the draft engine** | Actively rejected on measurement, twice: it raised RB=0 from 20% to 32% across 400 real drafts (M17), and P3 beat Experiment F while excluding it entirely (D55). Do not revisit without new evidence. |
| **Hardcoded positional caps or count targets to make rosters look normal** | Forbidden by the directive and by `CLAUDE.md`. Also unnecessary: if a shape is genuinely bad, the Mode B metrics will price it. |
| **Tuning against the current (unfixed) benchmark** | See §0. Any gain measured there is unattributable. |
| **Retracting or rewriting the D56–D60 record** | Those decisions were correctly reasoned on the evidence available. Label and supersede, as D56 did for the superflex era. Do not delete. |
| **A weekly lineup / in-season simulation as part of this phase** | Would materially improve the metric's realism, but it is a large new subsystem and `weekly_projection_snapshot` covers 2025 only (`docs/EVALUATION_LIMITATIONS.md`). Mode B's availability adjustment gets most of the benefit from data we already have. |

---

## Acceptance criteria

**Stage 1 (measurement):**
1. The consensus opponent fills every mandatory dedicated starting slot; derived from league
   config, not hardcoded; a no-K league is unaffected.
2. Both opponents reported side by side; no published number silently restated.
3. Forensic and production feasibility caps identical, asserted by test.
4. `pick_attribution.py` measures the shipped engine, verified by a test that the value base
   used matches the benchmark's.
5. Benchmark report shows unfilled mandatory slots per strategy.
6. All documentation errors in `docs/DRAFT_STRATEGY_FORENSIC_ANALYSIS.md` §9 corrected; P1-0
   reopened; a new decision-log entry records the artifact.
7. `make test` green, `make lint` clean, determinism byte-identical across two processes.

**Stage 3 (engine):**
8. A tier strictly beats the N0 control on mean starter points **against the fair opponent**,
   passing all four pre-registered gates.
9. Leave-one-season-out: the margin survives removal of any single season.
10. The K/DST timing regression is measurably reduced — mean first-K and first-DST round later
    than the control — or explicitly justified by measurement if not.
11. Alpha's consistency advantage (stdev, floor) is not given away: stdev no worse than the
    control's.

**Stage 4 (modes):**
12. Both modes runnable and reported; the tradeoff table populated with real numbers.
13. The default is chosen from the measurement and the reasoning recorded, including if the
    measurement says Mode A.

**Overall:**
14. No claim of beating consensus is made on any benchmark whose opponent cannot field a legal
    lineup.

---

## Sequencing summary

```
Stage 1  fix measurement (opponent, caps, attribution, reporting, docs)   <- no engine change
Stage 2  re-run baseline + M-tier ablation honestly                       <- no engine change
Stage 3  N0-N4 value-base ablation, pre-registered, fair opponent         <- the engine change
Stage 4  Mode A / Mode B split and tradeoff measurement
Stage 5  close the production/benchmark call-site gap
```

Stages 1 and 2 are prerequisites for 3. Stage 5 can proceed in parallel with 4.

**The single most important line in this document:** the current headline result is an artifact,
and the first job is to stop measuring the wrong thing — not to add another mechanism.
