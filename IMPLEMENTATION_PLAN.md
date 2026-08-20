# Fantasy Football ML/AI — Autonomous Implementation Plan

## Operating mode
Claude Code is expected to execute this plan autonomously after validating the repository and environment. It may revise sequencing when actual data/API constraints require it, but must preserve product requirements and document changes.

## Phase 0 — Repository and environment reconnaissance
- inspect entire repository
- read all project docs
- create/update CLAUDE.md
- identify current stack and existing code
- inspect credentials/config without exposing secrets
- validate source/API access
- identify contradictions
- produce internal implementation plan
- establish project state

Do not stop here; continue into Phase 1 unless a genuinely blocking decision exists.

## Phase 1 — Foundation
Parallelize:
- nflverse ingestion
- FantasyPros adapter
- CFBD adapter
- Sleeper adapter
- canonical identity framework

Then:
- normalize
- snapshot
- validate
- create DuckDB/Parquet schema
- create data quality tests
- create source health/status reporting

Definition:
all available core sources ingest or have explicit documented limitations; no fabricated success.

## Phase 2 — Historical/as-of feature system
- build player/team/college/market/evidence tables
- create as-of joins
- create feature generation
- enforce timestamp rules
- implement leakage tests
- create reproducible historical datasets

## Phase 3 — Baselines
- previous-year
- weighted 2-year
- FantasyPros ECR
- FantasyPros projections
- ADP-implied baseline where supportable

Build evaluation reports before advanced ML.

## Phase 4 — Established-player ML
- position-specific features
- regularized model
- CatBoost
- XGBoost challenger
- opportunity model
- team environment model
- ensemble only when justified by validation
- model registry

## Phase 5 — Uncertainty
- conformal or calibrated intervals
- p10/p25/median/p75/p90
- top-X probabilities
- calibration diagnostics

## Phase 6 — Rookie/prospect intelligence
- college-to-NFL feature pipeline
- draft capital
- athletic testing
- breakout classifier
- rookie-year projection
- dynasty trajectory
- historical comps as explanation
- historical rookie validation

## Phase 7 — Market/EDGE
- weighted market consensus
- expert accuracy weighting
- model-vs-market rank/points/probability edge
- BUY/HOLD/SELL/WATCH
- evidence requirement
- historical EDGE validation

## Phase 8 — Current-information engine
- evidence ingestion
- timestamped structured events
- depth chart/injury/role changes
- projection deltas
- market deltas
- explanation generation
- provenance

## Phase 9 — League context and decision engine
Support arbitrary leagues and the current target:
- 10 teams
- 2 QB
- 2 RB
- 2 WR
- 1 TE
- 2 FLEX

Implement:
- replacement level
- scarcity
- roster fit
- expected pick value
- next-pick survival probability
- draft recommendation
- waiver/FAAB recommendation
- trade/hold/buy/sell logic
- dynasty context

## Phase 10 — Agent/orchestrator runtime
Implement the explicit agent architecture where practical:
- structured task contracts
- state
- dependencies
- parallel task execution
- provenance
- critique/review
- disagreement resolution
- milestone gates
- failure/retry behavior

If the coding environment already provides an orchestration framework, adapt to it rather than inventing a redundant one.

## Phase 11 — Application/interface
After core validation:
- expose player intelligence
- EDGE/evidence
- rookie analysis
- league context
- roster
- draft
- waivers/FAAB
- recommendations
- explanations/provenance

Do not let UI logic become a second source of truth.

## Phase 12 — End-to-end hardening
- full test suite
- integration tests
- regression tests
- data refresh test
- historical reconstruction test
- model reproducibility test
- API failure tests
- ambiguous ID tests
- stale data tests
- security/secrets audit
- architecture review
- requirements traceability audit
- documentation audit

Then continue fixing until meaningful acceptance criteria are met.

## Autonomous loop
For each phase:
1. inspect current state
2. plan tasks
3. delegate/parallelize
4. implement
5. test
6. diagnose failures
7. fix
8. add regression tests
9. review architecture
10. compare against requirements
11. update state/docs
12. continue automatically

Do not stop merely because a phase's first implementation is complete.

## User interaction rule
Ask the user only when:
- proceeding requires an impossible-to-infer product decision
- a paid/licensed source is required and user authorization is needed
- a destructive/irreversible action is required
- two requirements are materially incompatible and cannot be resolved by preserving the more specific requirement
- external credentials/access cannot be obtained otherwise

Otherwise decide, document the assumption, and continue.

## Completion rule
Do not declare complete while:
- tests are failing
- core acceptance criteria are unverified
- meaningful requirements are unimplemented
- data sources silently fail
- leakage checks are absent
- recommendations bypass the validated intelligence/league layers
- provenance is missing
- major TODOs remain hidden

If a requirement is blocked by unavailable data, explicitly mark the capability as blocked/limited and implement the best supported fallback rather than fabricating it.
