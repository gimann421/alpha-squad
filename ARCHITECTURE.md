# Fantasy Football ML/AI — Definitive Technical/System Architecture

## 1. Architectural rule
Keep the system modular and auditable. Universal player intelligence is independent of league-specific decision logic.

```text
Data Sources
   ↓
Ingestion / Snapshots
   ↓
Canonical Identity + Validation
   ↓
Historical / Current Feature Store
   ↓
 ┌───────────────┬────────────────┬────────────────┐
 │ Projection ML │ Rookie ML      │ Market Layer   │
 └───────────────┴────────────────┴────────────────┘
          ↓             ↓              ↓
       Evidence / Current Information
                    ↓
             Ensemble / EDGE
                    ↓
       Universal Player Intelligence
                    ↓
          League Context Adapter
                    ↓
       League Decision / Strategy Engine
                    ↓
 Draft / Waiver / FAAB / Trade / Roster Recommendations
                    ↓
          Explanation + Provenance
```

## 2. Data layer
Use:
- nflverse for NFL history, rosters, draft/combine, IDs, PFR-derived snap/advanced data
- FantasyPros API for ECR, expert rankings, projections, ADP where accessible
- CFBD for college production/usage/context
- Sleeper API for league/player metadata, drafts, rosters, trending activity
- official NFL/team sources for current evidence

Store raw source snapshots separately from normalized data.

Never scrape around access controls.

## 3. Storage
DuckDB is the initial relational/query layer.
Parquet is the large-table/storage format.
Use immutable timestamped snapshots for market/evidence/projection data.

Suggested:
```text
data/raw/
data/processed/
data/features/
data/snapshots/
models/
predictions/
reports/
state/
```

## 4. Identity
Canonical player ID is the internal key. Maintain source mappings:
- nflverse
- FantasyPros
- Sleeper
- CFBD
- PFR
- Yahoo
- ESPN

Never join on name alone.

Ambiguous mappings go into a mapping-exception queue and block dependent pipelines until resolved or explicitly marked unsupported.

## 5. Model services/modules
### Established player
Position-specific models for QB/RB/WR/TE:
- historical baselines
- regularized linear
- CatBoost
- XGBoost challenger
- opportunity
- team environment
- uncertainty

### Rookie
Separate prospect/rookie pipeline and breakout classifier.

### Market
Weighted consensus and expert weighting.

### Evidence
Timestamped structured events; evidence never directly overwrites model output.

### Simulation
Later-stage Monte Carlo/team simulation.

## 6. Orchestrator
The project orchestrator is an engineering orchestration layer, not itself the source of fantasy truth.

It:
- decomposes tasks
- selects agents
- runs independent work in parallel
- passes structured artifacts
- preserves provenance
- invokes critique
- resolves disagreements
- gates milestones
- continues implementation autonomously

## 7. Agent interfaces
Use typed structured contracts wherever possible.

Minimum agent result:
```json
{
  "task_id": "TASK-001",
  "agent": "projection_ml",
  "status": "COMPLETE",
  "confidence": 0.82,
  "findings": [],
  "artifacts": [],
  "tests": [],
  "risks": [],
  "open_questions": [],
  "recommended_next_action": ""
}
```

Task states:
PLANNED, READY, RUNNING, BLOCKED, NEEDS_REVIEW, COMPLETE, FAILED, REJECTED.

Each task records dependencies and artifacts.

## 8. Agents
- Orchestrator/PM
- Data Engineering
- Player Identity
- Projection ML
- Rookie/Prospect ML
- Market/EDGE
- News/Evidence
- Evaluation/Scientific QA
- Fantasy Strategy/League Optimizer
- Research/External Validation as needed

### Ownership
Data: ingestion/normalization/schema/data tests.
Identity: canonical mappings.
ML: features/models/training/evaluation utilities.
Rookie: prospect features/models.
Market: market ingestion/edge.
News: evidence ingestion.
Evaluation: tests/evaluation/reports; should not silently alter model logic.
Strategy: league optimizer/draft/FAAB logic.
Orchestrator: cross-module architecture approval.

## 9. Agent communication
Prefer artifacts and schemas over prose:
- task manifests
- JSON result envelopes
- database tables
- model registry
- evidence records
- decision records

The orchestrator should be able to reconstruct what happened without reading a long chat transcript.

## 10. Provenance
Every prediction/decision should be tied to:
- data version
- feature version
- model version
- prediction timestamp
- input snapshot timestamp
- market snapshot
- evidence records
- decision-engine version
- league-context version

## 11. Validation gates
Gate 1 Data:
ingestion, IDs, validation, timestamps.

Gate 2 Baseline:
simple baselines + historical evaluation.

Gate 3 ML:
walk-forward performance + no leakage + baseline comparison.

Gate 4 Uncertainty:
calibration.

Gate 5 Rookie:
historical rookie evaluation.

Gate 6 EDGE:
market comparison + historical validation.

Gate 7 Strategy:
league-specific decisions.

Gate 8 Application:
interface exercises the validated core without bypassing provenance/decision logic.

## 12. Failure behavior
- API unavailable: record failure, preserve last known snapshot, mark data stale, do not fabricate.
- Ambiguous ID: quarantine mapping, do not silently join.
- Model test failure: diagnose, fix, add regression test.
- Source schema change: fail loudly and update adapter/tests.
- Agent disagreement: invoke critique/evaluation, preserve both positions, document resolution.
- Unvalidated model: mark UNVALIDATED and prevent it from becoming the default decision source.
- Missing required league context: return the limitation rather than pretending a league-specific recommendation is universal.

## 13. Reproducibility
A historical prediction must be reconstructable from stored snapshots. New season ingestion should require one documented command/workflow.

## 14. Technology
Initial:
- Python 3.12+
- DuckDB
- Parquet
- pandas or polars
- scikit-learn
- CatBoost
- XGBoost
- scipy
- statsmodels as useful
- pytest
- ruff
- Git
- visualization library as appropriate

Do not introduce heavy cloud infrastructure unless justified by actual requirements.

## 15. Security/licensing
- secrets only in environment/config
- never commit API keys
- respect source terms
- no bypassing access controls
- no fabricated data
- no distribution of proprietary source data without rights
