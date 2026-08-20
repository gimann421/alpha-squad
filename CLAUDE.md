# CLAUDE.md — Fantasy Football ML/AI Project Instructions

## Authority
Read and obey:
- `PRODUCT_SPEC.md`
- `ARCHITECTURE.md`
- `IMPLEMENTATION_PLAN.md`
- `ACCEPTANCE_CRITERIA.md`
- `AGENT_CONTRACTS.md`
- any original project documents retained in the repository

These define the approved product. Preserve requirements and decisions.

## Build behavior
Act autonomously. Plan internally, implement, test, fix, review, and continue. Do not stop after planning or after a phase. Ask the user only when a decision is genuinely impossible to infer and proceeding would cause substantial rework or an irreversible decision.

## Quality
- no fabricated data
- no future-data leakage
- no random primary time-series splits
- no untested claims
- no hidden failing tests
- add regression tests for bugs
- do not declare completion with meaningful unmet acceptance criteria

## Architecture
Universal player intelligence and league-specific decision logic are separate layers.

## Data
Core: nflverse, FantasyPros API, CFBD, Sleeper, official current information.
Never bypass access controls. Never use names as production player keys.

## Modeling
Use baselines first, then position-specific ML, uncertainty, rookie modeling, market EDGE, current information, league strategy.

## Agents
Use structured agent contracts and persistent state. Evaluation/QA is adversarial. Preserve provenance and resolve disagreements explicitly.

## Documentation
Update relevant docs when architecture, data contracts, assumptions, or acceptance criteria change. Record important decisions.

## Completion
A demo is not completion. Completion requires tested, documented, traceable acceptance criteria.
