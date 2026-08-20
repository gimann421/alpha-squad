# Fantasy Football ML/AI — Acceptance Criteria / Definition of Done

## Product completeness
- [ ] Redraft preseason projections/rankings exist.
- [ ] Dynasty rookie rankings exist.
- [ ] Dynasty overall rankings exist.
- [ ] In-season/ROS rankings exist.
- [ ] Projection ranges and probabilities exist.
- [ ] EDGE scores exist.
- [ ] Evidence/provenance explains material outliers.
- [ ] League-specific recommendations exist.
- [ ] Draft decisions exist.
- [ ] Waiver/FAAB decisions exist.
- [ ] Roster-aware decisions exist.
- [ ] Recommendation changes are explainable.

## Data
- [ ] nflverse ingestion works or limitation is explicitly documented.
- [ ] FantasyPros API integration works or limitation is explicitly documented.
- [ ] CFBD integration works or limitation is explicitly documented.
- [ ] Sleeper integration works or limitation is explicitly documented.
- [ ] Official/current evidence workflow exists.
- [ ] Raw/source snapshots are preserved.
- [ ] Canonical player IDs exist.
- [ ] Ambiguous mappings are quarantined.
- [ ] No production joins depend on names alone.
- [ ] Data quality checks fail loudly.
- [ ] API/source failures never fabricate success.

## Historical integrity
- [ ] Historical predictions can be reconstructed as-of a specified date.
- [ ] Every time-sensitive input has captured/effective timestamps.
- [ ] Primary evaluation uses walk-forward validation.
- [ ] No future injuries, final ADP, end-of-season depth charts, or target outcomes leak into historical features.
- [ ] Leakage tests exist and pass.

## Modeling
- [ ] Simple baselines exist.
- [ ] Position-specific established-player models exist.
- [ ] CatBoost exists.
- [ ] XGBoost challenger exists or is explicitly rejected with evidence.
- [ ] Opportunity modeling exists.
- [ ] Team environment modeling exists.
- [ ] Rookie model is separate from established-player model.
- [ ] Rookie breakout probability exists.
- [ ] Draft capital is explicit.
- [ ] Uncertainty intervals exist.
- [ ] Probability calibration is measured.
- [ ] Model versions are tracked.
- [ ] Model performance is compared against baselines.

## Market/EDGE
- [ ] FantasyPros ECR is a market baseline when available.
- [ ] ADP is tracked when available.
- [ ] Sleeper/KTC are treated as separate signals, not truth.
- [ ] Expert weighting uses demonstrated accuracy where data permits.
- [ ] Rank edge, points edge, and probability edge exist.
- [ ] A raw ranking discrepancy cannot alone produce a strong EDGE.
- [ ] BUY/HOLD/SELL/WATCH are evidence-backed.
- [ ] Historical EDGE performance is evaluated.

## Evidence
- [ ] Evidence events are timestamped.
- [ ] Evidence has source/provenance.
- [ ] Evidence strength is structured.
- [ ] Strong/medium/weak hierarchy is implemented.
- [ ] News does not directly overwrite model projections.
- [ ] Material projection changes have reasons.

## League decision engine
- [ ] Universal player intelligence is separate from league context.
- [ ] Arbitrary league settings can be represented.
- [ ] Target league settings are supported: 10 teams, 2 QB, 2 RB, 2 WR, 1 TE, 2 FLEX.
- [ ] Replacement level is calculated.
- [ ] Positional scarcity is calculated.
- [ ] Roster fit is calculated.
- [ ] Expected pick value exists.
- [ ] Next-pick survival probability exists.
- [ ] Draft recommendation includes alternatives and reasoning.
- [ ] Waiver/FAAB recommendations include roster fit and replacement.
- [ ] Dynasty decisions account for future value.

## Agent/orchestrator
- [ ] Orchestrator can decompose work.
- [ ] Agents have explicit responsibilities.
- [ ] Structured task/result contracts exist.
- [ ] Dependencies are explicit.
- [ ] Independent tasks can run in parallel.
- [ ] Provenance is preserved across agent outputs.
- [ ] Critique/review can be invoked.
- [ ] Agent disagreements are explicitly resolved.
- [ ] Evaluation/QA can reject unsupported claims.
- [ ] Agent failures are retried/recovered or surfaced.
- [ ] Shared project state exists.
- [ ] Milestone state is persistent.

## Engineering quality
- [ ] CLAUDE.md contains durable project instructions.
- [ ] README documents setup and workflows.
- [ ] Data/model/validation docs exist.
- [ ] Tests run automatically/continuously.
- [ ] Bugs discovered during implementation get regression tests.
- [ ] Secrets are not committed.
- [ ] Ruff/static checks pass.
- [ ] Unit tests pass.
- [ ] Integration tests pass where configured.
- [ ] End-to-end workflow succeeds.
- [ ] New season ingestion is documented and repeatable.
- [ ] Architecture review completed.
- [ ] Requirements traceability review completed.

## Application/interface
- [ ] The interface exposes the validated player intelligence.
- [ ] EDGE/evidence can be inspected.
- [ ] Rookie evaluation can be inspected.
- [ ] League context can be loaded.
- [ ] Roster-aware recommendations can be generated.
- [ ] Draft/waiver/FAAB recommendations can be generated.
- [ ] Recommendation explanations show relevant evidence/provenance.
- [ ] UI does not duplicate or bypass core model/decision logic.

## Completion standard
The project is not "done" because a demo runs.

It is done only when the implemented scope is tested, documented, traceable to requirements, and meaningful acceptance criteria are satisfied. Any blocked capability must be explicitly marked blocked/limited with the reason and fallback.
