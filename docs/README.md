# docs/ — authority map

**What this file is.** An index of where each kind of information authoritatively lives, and
whether a given document is **shared**, **draft-specific** or **weekly-specific**.

**Why it exists (W1/D109; extended W1.1-W2/D110).** Alpha Squad now runs two research programs — the draft-choice
program (D86–D108, closed) and the weekly-ranking program (W1→). `docs/` is a flat directory of
40+ files that mixes product authority, shared methodology, draft findings, living state and the
decision log. With one program that was navigable by memory; with two it is not, and the
highest-risk failure mode becomes a reader applying a draft-program conclusion to a weekly
question. **This map fixes that by classifying, not by moving:** no file was relocated, so no
citation in any existing document breaks.

---

## Hierarchy of authority

Most authoritative first. When two documents disagree, the higher tier wins.

| tier | what | where | scope |
|---|---|---|---|
| **1** | Product & architecture authority | `/PRODUCT_SPEC.md`, `/ARCHITECTURE.md`, `/ACCEPTANCE_CRITERIA.md`, `/AGENT_CONTRACTS.md`, `/IMPLEMENTATION_PLAN.md`, `/CLAUDE.md` | shared |
| **2** | **Decisions** | **`DECISIONS.md`** — one append-only, D-numbered log for the whole project | shared |
| **3** | Program entry points | `D108_PROGRAM_CLOSEOUT.md` (draft) · **`weekly/W8_ECR_ADVANTAGE_RESULTS.md`** (weekly — start there; then W7 for opportunity, W6 for the objective, W5 for the diagnosis, W4 for the FLEX question, W3 for what Alpha can do, W2 for the benchmark, W1.1 for the data story) | per-program |
| **4** | Methodology / benchmark definition | `BENCHMARK_SPEC.md` (draft) · `weekly/W2_PREREGISTRATION.md` (weekly) | per-program |
| **5** | Data & format contracts | `DATA_SOURCES.md`, `TARGET_FORMAT_1QB.md` | shared |
| **6** | Living state | `PROJECT_STATE.md`, `TRACEABILITY.md` | shared |
| **7** | Phase findings | `D##_*.md`, `weekly/W#_*.md` | per-phase; historical once superseded |

**One decision log, deliberately.** A separate `WEEKLY_DECISIONS.md` would create the parallel
source of truth CLAUDE.md and the W1 brief both warn against, and would make "has this been
decided?" a two-file question. The weekly program continues the D-sequence (it opens at **D109**; W4 is **D112**, W5 is **D113**, W6 is **D114**, W7 is **D115**, W8 is **D116**)
and uses W-numbers only for *phases*: **D-numbers say what was decided, W-numbers say which phase
decided it.**

---

## Where to look for a given question

| question | authoritative source |
|---|---|
| What is Alpha? What is the product? | `/PRODUCT_SPEC.md`, `/README.md` |
| What is the current product goal for weekly rankings? | `weekly/W1_FOUNDATION_AUDIT.md` §0 |
| How good is the ECR benchmark, and what counts as a real improvement? | `weekly/W2_ECR_BENCHMARK_RESULTS.md` §2-§3 |
| What can the existing Alpha weekly model actually do? | `weekly/W3_ALPHA_BENCHMARK_RESULTS.md` |
| Is cross-position calibration worth building for the FLEX board? | `weekly/W4_FLEX_FORENSICS_RESULTS.md` §1 (no — verdict D) |
| Does Alpha's ranking quality really collapse at the top of a positional board? | `weekly/W5_TOPBOARD_FORENSICS.md` §3 (the drop is range restriction; a real cliff sits under it at RB/WR) |
| Which missing information would most improve weekly rankings? | `weekly/W5_TOPBOARD_FORENSICS.md` §16 (none clears the materiality bar) |
| Can the injury report be used at a Friday cutoff? | `weekly/W5_TOPBOARD_FORENSICS.md` §9 (no — 0.2% of rows survive a strict cutoff) |
| Would training on a higher part of the outcome fix the top of the board? | `weekly/W6_UPPER_OUTCOME_RESULTS.md` §1 (no — verdict NO EFFECT) |
| Why did changing the training target not move the rankings? | `weekly/W6_UPPER_OUTCOME_RESULTS.md` §5 (it is nearly a monotone rescaling — board rank correlation 0.99+) |
| Can a player's opportunity be predicted before Friday? | `weekly/W7_OPPORTUNITY_RESULTS.md` (partly — rank correlation 0.71 / 0.67 / 0.63; ~84–86% of it is already in Alpha) |
| Would adding pre-Friday opportunity features to Alpha fix the top of the board? | `weekly/W7_OPPORTUNITY_RESULTS.md` §8 (no — RB null, WR top-10 slightly worse; verdict HARM) |
| Why does ECR beat Alpha at the top of the board? | `weekly/W8_ECR_ADVANTAGE_RESULTS.md` (anticipated opportunity beyond pre-Friday data — 75–94% of the lead; efficiency is small and not robust) |
| Why is Alpha's FLEX top-10 short of TEs, and should that be fixed? | `weekly/W4_FLEX_FORENSICS_RESULTS.md` §8-§9 (it is not an error) |
| Which weekly ECR data exists, in which source, at what depth? | `weekly/W11_FANTASYPROS_FLEX_AUDIT.md` |
| What has already been tested, and what was concluded? | `DECISIONS.md` (all) → the phase doc it names |
| What was rejected, and why? | `DECISIONS.md`; `D108_PROGRAM_CLOSEOUT.md` §2 for the draft program |
| Is this finding draft-specific or weekly-specific? | this file's scope column; `weekly/W1_FOUNDATION_AUDIT.md` §10.3 for the methodology split |
| What methodology must be preserved? | `weekly/W1_FOUNDATION_AUDIT.md` §10.3 (shared vs program-specific) |
| Which data sources work, and how? | `DATA_SOURCES.md`; weekly-specific coverage in `weekly/W1_FOUNDATION_AUDIT.md` §4–§6 |
| Which acceptance criterion does module X satisfy? | `TRACEABILITY.md` |
| What milestone are we on? | `PROJECT_STATE.md` |
| What is experimental vs production? | `src/alpha_squad/evaluation/**` is research; `models/`, `league/`, `api/` are production. `evaluation/weekly/__init__.py` states the contract for the weekly package. |
| May I reopen the draft question? | `D108_PROGRAM_CLOSEOUT.md` §4 — seven named criteria, nothing else |

---

## Document classification

### Shared — applies to the whole project

| file | kind |
|---|---|
| `DECISIONS.md` | decision log (D1–) — **the** record |
| `PROJECT_STATE.md` | living milestone status |
| `TRACEABILITY.md` | acceptance criteria → module/test/report |
| `DATA_SOURCES.md` | source reachability & contracts |
| `TARGET_FORMAT_1QB.md` | the default league format (D58) |
| `CURRENT_STATE_AUDIT.md` | whole-system audit |
| `IMPLEMENTATION_GAP_ANALYSIS.md` | spec-vs-implementation gaps |

### Weekly-ranking program (W1→)

| file | kind |
|---|---|
| `weekly/W1_FOUNDATION_AUDIT.md` | foundation audit — **carries a correction banner; two of its findings were retracted/downgraded by W1.1** |
| `weekly/W11_FANTASYPROS_FLEX_AUDIT.md` | **the FLEX/Half-PPR data correction** — which sources have what, and the acquisition limits |
| `weekly/W2_PREREGISTRATION.md` | pre-registered W2 experiment + amendment A1 (both written before results) |
| `weekly/W2_ECR_BENCHMARK_RESULTS.md` | the ECR benchmark, the noise floor, scope/exclusions |
| `weekly/W3_PREREGISTRATION.md` | pre-registered W3 evaluation + the Alpha model audit (written before results) |
| `weekly/W3_ALPHA_BENCHMARK_RESULTS.md` | what the existing Alpha weekly model can do, three-way comparison — **one finding superseded by W4** (the "pooling destroys 84%" claim) |
| `weekly/W4_PREREGISTRATION.md` | pre-registered W4 forensic audit + a priori predictions (written before any counterfactual ran) |
| `weekly/W4_FLEX_FORENSICS_RESULTS.md` | the FLEX forensic audit: verdict D, and why calibration must not be built — **§3.2's conditional-correlation reading is refined by W5** |
| `weekly/W5_PREREGISTRATION.md` | pre-registered W5 forensic audit + a priori predictions + amendment A1 (written before the instruments) |
| `weekly/W5_TOPBOARD_FORENSICS.md` | the top-of-board audit: what the cliff is, what does not explain it, and the W6 design |
| `weekly/W6_PREREGISTRATION.md` | pre-registered W6 experiment + a priori predictions + amendment A1 (written before any comparative result) |
| `weekly/W6_UPPER_OUTCOME_RESULTS.md` | the upper-outcome experiment: verdict NO EFFECT, and why the objective does not control the ordering |
| `weekly/W7_PREREGISTRATION.md` | pre-registered W7 audit: timing classes, fixed feature sets, verdict order, a priori predictions (written before any forecast) |
| `weekly/W7_OPPORTUNITY_RESULTS.md` | the opportunity-forecastability audit: what is predictable before Friday, what Alpha already has, verdict HARM (= NO EFFECT) |
| `weekly/W8_PREREGISTRATION.md` | pre-registered W8 diagnostic: the exact decomposition, buckets, pair tests, verdict rules, predictions + amendment A1 (written before any comparison) |
| `weekly/W8_ECR_ADVANTAGE_RESULTS.md` | **current program entry point** — where ECR's top-of-board advantage comes from: verdict MIXED, robust half INFORMATION |

### Draft-choice program (D86–D108, CLOSED)

Entry point: **`D108_PROGRAM_CLOSEOUT.md`**. Read it before any of the phase docs below; it
states what was and was not established, and the only conditions for reopening.

`D87_SHORTLIST_REPLICATION.md` · `D88_O1_POWER_REPLICATION.md` · `D89_2020_REPLICATION.md` ·
`D90_CROSS_FORMAT_GENERALIZATION.md` · `D91_O1_ADVANTAGE_ATTRIBUTION.md` ·
`D92_BOARD_VINTAGE_INSTRUMENT.md` · `D99_PROJECTION_CALIBRATION.md` ·
`D100_FEATURE_SIGNAL_DIAGNOSTIC.md` · `D101_Y0_Y3_IDENTIFICATION.md` ·
`D102_PICK_LEVEL_OBJECTIVE.md` · `D103_PICK_LEVEL_OBJECTIVE.md` · `D104_ECR_FLOOR.md` ·
`D105_OBJECTIVE_SENSITIVITY.md` · `D106_WEEKLY_SENSITIVITY.md` ·
`D107_RESEARCH_CONSOLIDATION_AUDIT.md`

> **`D106_WEEKLY_SENSITIVITY.md` is draft-specific despite its name.** "Weekly" there means the
> draft program's *weekly lineup objective* — scoring a season of a fixed drafted roster week by
> week. It is not about weekly rankings and must not be cited as though it were. See
> `weekly/W1_FOUNDATION_AUDIT.md` §10.3.

### Draft engine & decision layer — earlier draft-specific work

`BENCHMARK_SPEC.md` (draft benchmark definition) · `ALPHA_VS_BASELINES_EVALUATION.md` ·
`DECISION_LAYER_FINAL_REPORT.md` · `DECISION_LAYER_INVESTIGATION.md` ·
`DRAFT_CONTROLLED_EXPERIMENTS.md` · `DRAFT_DECISION_ENGINE_INVESTIGATION.md` ·
`DRAFT_ENGINE_FORENSIC_AUDIT.md` · `DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` ·
`DRAFT_OBJECTIVE_MODES.md` · `DRAFT_OBJECTIVE_RESEARCH.md` ·
`DRAFT_STRATEGY_FORENSIC_ANALYSIS.md` · `DRAFT_STRATEGY_NEXT_PHASE_PLAN.md` ·
`FORMAT_MIGRATION_DIAGNOSTIC.md` · `OPENING_DRAFT_AUDIT.md` ·
`VALUATION_LEGALITY_SEPARATION.md`

### Projection & evaluation methodology — mostly shared, draft-scoped evidence

`EVALUATION_PLAN.md` · `EVALUATION_LIMITATIONS.md` · `PROJECTION_INVESTIGATION_FINAL.md` ·
`RB_AVAILABILITY_PREREGISTRATION.md` (executed, gates failed, nothing shipped — kept as the
historical record and as the template for how a pre-registration is written and honoured)

---

## Conventions for adding a document

1. **A new finding appends to `DECISIONS.md`** with the next D-number, and links its phase doc.
   The log is the record; the phase doc is the detail.
2. **A weekly-program phase doc goes in `docs/weekly/`** as `W#_TOPIC.md` and is listed above.
3. **A pre-registration is committed before the experiment runs**, and amended only in writing,
   with a reason (D70, D106).
4. **An instrument that produced a number must be committed**, not run ad hoc — D92 had to
   retract a finding because its runner never was.
5. **State scope in the document's own header.** A finding that is draft-specific says so, in
   the document, not only here.
