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

**Verified environment status (see `docs/DATA_SOURCES.md` and `docs/DECISIONS.md` D3 for full
detail; re-verify with `alpha-squad sources status` before assuming this is still current):**
nflverse, DynastyProcess, cfbfastR-data, and ffopportunity are reachable via
`raw.githubusercontent.com` / GitHub release assets and are the primary data path. Direct calls to
`api.sleeper.app`, `api.fantasypros.com`, `api.collegefootballdata.com`, `keeptradecut.com`, and
`site.api.espn.com` are blocked by this environment's egress policy (403 at CONNECT, not a
credentials problem). Adapters for all of them are implemented to the same interface as the
working sources and raise `SourceBlockedError` → `BLOCKED_BY_POLICY` in the snapshot registry
rather than returning empty or fabricated data; they activate automatically if the policy changes.
DynastyProcess's `db_fpecr`/`values-players` cover the FantasyPros ECR/market signal;
cfbfastR-data covers CFBD's college-production role; DynastyProcess `values-players`/`values-picks`
cover KeepTradeCut's dynasty-value role. Do not re-attempt the blocked hosts as a "fix" — extend
the substitute adapters instead, and only revisit direct access if the user supplies credentials
or the policy is confirmed changed.

## Modeling
Use baselines first, then position-specific ML, uncertainty, rookie modeling, market EDGE, current information, league strategy.

## Agents
Use structured agent contracts and persistent state. Evaluation/QA is adversarial. Preserve provenance and resolve disagreements explicitly.

## Documentation
Update relevant docs when architecture, data contracts, assumptions, or acceptance criteria change. Record important decisions.

## Completion
A demo is not completion. Completion requires tested, documented, traceable acceptance criteria.

## Engineering environment
- Python 3.12 via `uv` (`.python-version` pins it; environment default is 3.11, do not use it).
  `uv sync --extra dev` installs; `make test`/`make lint` are the standard gates.
- DuckDB (`data/alpha_squad.duckdb`, gitignored) is the query layer; Parquet under `data/raw/` for
  immutable timestamped snapshots. Never commit anything under `data/`, `models/`, `predictions/`,
  `reports/`, or `state/` — they are gitignored and reproducible from `alpha-squad ingest`.
- Test fixtures under `tests/fixtures/` are schema-accurate synthetic data, not copies of real
  source data (licensing; also keeps the suite offline and fast). `pytest` deselects the
  `network` marker by default — use `make test-network` to hit real sources.
- Project state lives in `docs/PROJECT_STATE.md` (milestone status),
  `docs/DECISIONS.md` (append-only assumption/decision log), and
  `docs/TRACEABILITY.md` (acceptance-criteria → module/test/report mapping, created in M13).
  Update them as part of finishing a milestone, not as an afterthought.
