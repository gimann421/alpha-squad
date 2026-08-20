# Fantasy Football ML/AI — Agent Contracts and Orchestration Schemas

## Agent registry

### orchestrator
Owns planning, delegation, state, synthesis, quality gates, and milestone completion.

### data_engineering
Owns source ingestion, normalization, snapshots, data validation, and source health.

### player_identity
Owns canonical IDs, source mappings, ambiguity handling.

### projection_ml
Owns established-player features, baselines, CatBoost/XGBoost, opportunity/team models, uncertainty.

### rookie_ml
Owns college-to-NFL features, draft capital, prospect/rookie models, breakout probability, dynasty trajectory.

### market_edge
Owns market snapshots, expert weighting, market consensus, rank/points/probability edge.

### news_evidence
Owns current-information collection and structured evidence events.

### evaluation_qa
Owns leakage detection, validation, calibration, baseline comparisons, regression tests, and adversarial review.

### fantasy_strategy
Owns league context, replacement/scarcity, draft, waiver/FAAB, trade/roster decision logic.

### research_validation
Optional. Performs independent research when structured data cannot answer a question.

## Task contract

```json
{
  "task_id": "TASK-001",
  "agent": "projection_ml",
  "objective": "Build and validate WR baseline projection features",
  "priority": "HIGH",
  "depends_on": ["DATA-001", "ID-001"],
  "inputs": ["feature_schema_v1"],
  "acceptance_criteria": [
    "features are reproducible",
    "no future data is used",
    "tests pass"
  ],
  "artifacts_expected": [
    "feature module",
    "tests",
    "evaluation report"
  ]
}
```

## Result contract

```json
{
  "task_id": "TASK-001",
  "agent": "projection_ml",
  "status": "COMPLETE",
  "confidence": 0.87,
  "findings": [],
  "artifacts": [],
  "tests": [
    {"name": "no_future_leakage", "status": "PASS"}
  ],
  "risks": [],
  "open_questions": [],
  "recommended_next_action": "Run QA gate"
}
```

## Evidence contract

```json
{
  "event_id": "EV-001",
  "player_id": "canonical-id",
  "event_date": "2026-08-17",
  "captured_at": "2026-08-17T14:00:00Z",
  "event_type": "depth_chart_change",
  "source": "official_team",
  "source_url": "...",
  "strength": 0.95,
  "structured_impact": {
    "depth_chart_rank": 1
  },
  "summary": "Structured summary"
}
```

## Prediction contract

```json
{
  "prediction_id": "PRED-001",
  "prediction_date": "2026-08-17",
  "player_id": "canonical-id",
  "model_version": "wr_catboost_v1",
  "data_version": "snapshot-2026-08-17",
  "feature_version": "wr_features_v1",
  "target": "ppr_points",
  "p10": 90,
  "p25": 112,
  "median": 142,
  "p75": 171,
  "p90": 205,
  "top12_prob": 0.07,
  "top24_prob": 0.18,
  "confidence": 0.72
}
```

## Edge contract

```json
{
  "player_id": "canonical-id",
  "prediction_date": "2026-08-17",
  "model_rank": 38,
  "market_rank": 71,
  "rank_edge": 33,
  "projected_points_edge": 24.5,
  "probability_edge": 0.11,
  "evidence_score": 0.84,
  "confidence": 0.72,
  "action": "BUY",
  "reasons": ["..."],
  "provenance": {
    "prediction_id": "PRED-001",
    "market_snapshot_id": "MKT-001",
    "evidence_ids": ["EV-001"]
  }
}
```

## League context contract

```json
{
  "league_id": "league-001",
  "format": "dynasty",
  "teams": 10,
  "scoring": {
    "ppr": true
  },
  "lineup": {
    "QB": 2,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "FLEX": 2
  },
  "roster": {},
  "draft_state": {},
  "waiver_state": {},
  "faab": {},
  "future_picks": {}
}
```

## Decision contract

```json
{
  "decision_id": "DEC-001",
  "decision_type": "draft_pick",
  "league_id": "league-001",
  "recommendation": "Player A",
  "alternatives": ["Player B", "Player C"],
  "expected_value": 0.81,
  "confidence": 0.77,
  "reasons": [],
  "risks": [],
  "provenance": {
    "player_predictions": [],
    "edge_snapshots": [],
    "league_context_version": "..."
  }
}
```

## Orchestrator conflict protocol
When agents disagree:
1. preserve each result
2. identify disagreement type: data/model/market/evidence/strategy
3. run targeted critique
4. ask evaluation/QA to test empirical claims
5. resolve using validated evidence and explicit assumptions
6. record a decision
7. never silently discard the minority result

## Agent failure protocol
- retry transient failures
- invalidate partial artifacts if consistency is compromised
- preserve logs
- create regression test when a software defect caused failure
- escalate only when the user must make an irreversible or genuinely unknowable decision
