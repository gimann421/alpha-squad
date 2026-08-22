# Traceability — ACCEPTANCE_CRITERIA.md → module / test / report

Every checkbox from `ACCEPTANCE_CRITERIA.md`, mapped to what satisfies it. Status legend:

- ✅ **MET** — implemented against real data, tested, and (where applicable) verified live.
- ⚠️ **LIMITED** — implemented as far as this environment allows; the gap and fallback are
  named explicitly, not silently dropped. See the referenced `docs/DECISIONS.md` entry.
- ❌ **BLOCKED** — not reachable in this environment; the adapter/interface exists and will
  activate unchanged if the blocker lifts, but no live data flows through it today.

This document is itself the deliverable for "Requirements traceability review completed"
below, and was produced/verified in M13 alongside a real bug-fix pass (docs/DECISIONS.md
D28/D29) — every line here reflects the system's actual, current, post-fix state, not the
state at the time each milestone was first built.

## Product completeness

| Criterion | Status | Where |
|---|---|---|
| Redraft preseason projections/rankings exist | ✅ | `models/established/season_level.py` (M5), `models/baselines/` (M4); `/rankings` API, `RankingsView` |
| Dynasty rookie rankings exist | ✅ | `models/rookie/train.py` (M7); `/rookies` API, `RookiesView` |
| Dynasty overall rankings exist | ✅ | `market/dynasty_values.py` (dynasty market value) blended with EDGE via `league/trade.py` |
| In-season/ROS rankings exist | ✅ | `models/established/train.py::_persist_weekly_projections`, evidence-adjusted via `evidence/prior_update.py` (M9) |
| Projection ranges and probabilities exist | ✅ | `models/uncertainty/` (M6): p10/p25/p50/p75/p90, top-12/24 probability |
| EDGE scores exist | ✅ | `market/edge.py` (M8) |
| Evidence/provenance explains material outliers | ✅ | `evidence/events.py`, `projection_deltas` (M9); `/provenance/{id}` |
| League-specific recommendations exist | ✅ | `league/` (M10) |
| Draft decisions exist | ✅ | `league/draft.py::recommend_draft_pick` |
| Waiver/FAAB decisions exist | ✅ | `league/waiver.py::recommend_waiver_pickup` |
| Roster-aware decisions exist | ✅ | `league/roster.py::roster_fit_multiplier` |
| Recommendation changes are explainable | ✅ | `decisions.reasons`, `projection_deltas.reason`, `/provenance/{id}` traces every field to a source row |

## Data

| Criterion | Status | Where |
|---|---|---|
| nflverse ingestion works or limitation documented | ✅ | `sources/nflverse.py` — AVAILABLE, real data 2015-2025 ingested |
| FantasyPros API integration works or limitation documented | ⚠️ | `sources/fantasypros.py` implemented; network layer confirmed open 2026-08-22 (D31, real `403 Forbidden` app response with no key) — now credential-gated (paid `FANTASYPROS_API_KEY`), not policy-blocked; substituted by DynastyProcess `db_fpecr` (D3) for the ECR signal itself in the meantime |
| CFBD integration works or limitation documented | ⚠️ | `sources/cfbd.py` implemented; network layer confirmed open 2026-08-22 (D31, real "missing Bearer key" app response) — now credential-gated (free `CFBD_API_KEY`), not policy-blocked; substituted by cfbfastR-data (D3) for college production in the meantime |
| Sleeper integration works or limitation documented | ✅ | `sources/sleeper.py` — became AVAILABLE 2026-08-22 when the environment's egress policy changed (D31), verified with real data (state/players/trending adds+drops); league context remains config-driven (YAML, D6) rather than live-synced, a product choice, not a data-access limitation |
| Official/current evidence workflow exists | ✅ | `evidence/events.py` — depth chart, injury, roster, usage-share detectors on real nflverse data |
| Raw/source snapshots are preserved | ✅ | `storage/snapshots.py`, immutable `data/raw/<source>/<dataset>/captured_at=.../`, `snapshot_registry` |
| Canonical player IDs exist | ✅ | `identity/canonical.py`, `asq_######`, spine = nflverse `players.gsis_id` |
| Ambiguous mappings are quarantined | ✅ | `identity/exceptions.py`; `tests/unit/test_canonical_identity.py::test_ambiguous_within_batch_is_quarantined_not_inserted`, `test_cross_source_collision_is_quarantined_and_original_mapping_kept` |
| No production joins depend on names alone | ✅ | every cross-source join keys on gsis_id/cfb_player_id/pfr_id etc., never `display_name` |
| Data quality checks fail loudly | ✅ | `require_snapshot` raises rather than returning empty; M1 schema-drift tests |
| API/source failures never fabricate success | ✅ | `SourceBlockedError`→`BLOCKED_BY_POLICY` in the registry; M12 Gate 8 (killing the API breaks the UI rather than serving stale/fabricated data) |

## Historical integrity

| Criterion | Status | Where |
|---|---|---|
| Historical predictions can be reconstructed as-of a specified date | ✅ | `features/panel.py::features_as_of`; `market_snapshot` filtered by `scrape_date <= as_of` (`models/baselines/market_implied.py`, `league/draft.py`) |
| Every time-sensitive input has captured/effective timestamps | ✅ | `snapshot_registry.captured_at`, `games.game_date`, `market_snapshot.scrape_date`, `evidence_events.detected_at` |
| Primary evaluation uses walk-forward validation | ✅ | expanding-window throughout M4-M8; `MIN_TRAIN_SEASON`/`target_season - 1` pattern, never a random split |
| No future injuries/final ADP/end-of-season depth charts/target outcomes leak | ✅ | `tests/leakage/test_player_week_features_leakage.py` (poison-future-data, target-isolation, rebuild-invariance) |
| Leakage tests exist and pass | ✅ | `tests/leakage/` — part of `make test`, verified green in M13's final run |

## Modeling

| Criterion | Status | Where |
|---|---|---|
| Simple baselines exist | ✅ | `models/baselines/` — previous-year, weighted-2yr, per-game-rate, ECR-implied |
| Position-specific established-player models exist | ✅ | `models/established/train.py`, per QB/RB/WR/TE |
| CatBoost exists | ✅ | `ml_catboost` in `MODEL_SPECS` |
| XGBoost challenger exists or is explicitly rejected with evidence | ✅ | `ml_xgboost`; compared against every other component in `evaluation_results`, real numbers in `reports/established_ml_evaluation.md` |
| Opportunity modeling exists | ✅ | `ml_opportunity_only` |
| Team environment modeling exists | ✅ | `ml_team_environment_only` (M5); correlated team-season simulation (M13, `models/simulation/`) |
| Rookie model is separate from established-player model | ✅ | `models/rookie/` is a fully separate pipeline/feature set, walk-forward by draft class |
| Rookie breakout probability exists | ✅ | `ml_rookie_breakout_*` classifiers |
| Draft capital is explicit | ✅ | `models/rookie/features.py` draft-capital/pick-value-curve feature |
| Uncertainty intervals exist | ✅ | M6 quantile models + split-conformal calibration |
| Probability calibration is measured | ✅ | `reports/calibration_report.md` — real out-of-sample coverage vs. nominal |
| Model versions are tracked | ✅ | model registry (`_register_model`), `VALIDATED`/`UNVALIDATED` |
| Model performance is compared against baselines | ✅ | same `evaluation_results` table for both, `evaluate_and_record` |

## Market/EDGE

| Criterion | Status | Where |
|---|---|---|
| FantasyPros ECR is a market baseline when available | ✅ | via DynastyProcess `db_fpecr` (real historical ECR, D3); `market/consensus.py` |
| ADP is tracked when available | ⚠️ | no direct ADP series is reachable in this environment; ECR-implied (isotonic rank→points, D17) and dynasty market value are the documented substitutes — not literal ADP |
| Sleeper/KTC are treated as separate signals, not truth | ⚠️ | Sleeper is now AVAILABLE (D31) but nothing yet consumes it as a market/decision signal (no code change implied by reachability alone — a product decision, not built); KTC has no formal adapter and its dynasty-value role is covered by DynastyProcess `values-players`/`values-picks` (D3); either way, architecturally kept as a market signal EDGE compares against, never a source of truth the model defers to |
| Expert weighting uses demonstrated accuracy where data permits | ⚠️ | only *consensus* ECR is reachable, not per-expert rankings (needs the blocked FantasyPros API); weighting is applied at the source level (ECR vs. dynasty value vs. model) instead (D4) |
| Rank edge, points edge, and probability edge exist | ✅ | `market/edge.py` `EdgeContract` fields |
| A raw ranking discrepancy cannot alone produce a strong EDGE | ✅ | `classify_action`'s hard gating rule; `tests/unit/test_edge.py::TestClassifyActionGatingRule` |
| BUY/HOLD/SELL/WATCH are evidence-backed | ✅ | `evidence_score` veto below `EVIDENCE_CONTRADICTION_THRESHOLD` (D23) |
| Historical EDGE performance is evaluated | ✅ | `edge validate`, `reports/edge_validation.md`; BUY cohort beat market-implied points in 3 of 4 scored seasons post-M13-fix, honestly reported either way (D21, D28) |

## Evidence

| Criterion | Status | Where |
|---|---|---|
| Evidence events are timestamped | ✅ | `evidence_events.detected_at` |
| Evidence has source/provenance | ✅ | `evidence_events.source_snapshot_id` |
| Evidence strength is structured | ✅ | `evidence/taxonomy.py` |
| Strong/medium/weak hierarchy is implemented | ⚠️ | Strong tier has real detectors on officially-sourced nflverse data; Medium/Weak are registered vocabulary with a manual-entry path but no reachable text/news source to detect them automatically (D5, D22) |
| News does not directly overwrite model projections | ✅ | `evidence/prior_update.py::apply_evidence_adjustment`, bounded to `MAX_ADJUSTMENT_PCT = 0.15`; tested |
| Material projection changes have reasons | ✅ | `projection_deltas.reason` + `evidence_ids` |

## League decision engine

| Criterion | Status | Where |
|---|---|---|
| Universal player intelligence is separate from league context | ✅ | architectural split: M1-M9 (`identity/`, `features/`, `models/`, `market/`, `evidence/`) never import from `league/`; only `league/` reads the universal layer |
| Arbitrary league settings can be represented | ✅ | `league/context.py::LeagueContext` (pydantic), YAML-driven |
| Target league settings are supported | ✅ | `config/league_configs/target_league.yaml` — 10 teams, 2QB/2RB/2WR/1TE/2FLEX |
| Replacement level is calculated | ✅ | `league/replacement.py::replacement_level`, derived from the league's own starting-slot config (verified: 2QB league's QB replacement sits at real rank ~20-24, materially different from a 1QB league) |
| Positional scarcity is calculated | ✅ | `positional_scarcity` |
| Roster fit is calculated | ✅ | `roster_fit_multiplier` |
| Expected pick value exists | ✅ | `recommend_draft_pick`'s VORP × fit × confidence score |
| Next-pick survival probability exists | ✅ | `next_pick_survival_probability` (Uniform over ECR best/worst) |
| Draft recommendation includes alternatives and reasoning | ✅ | `DraftRecommendation.alternatives`/`.reasons` |
| Waiver/FAAB recommendations include roster fit and replacement | ✅ | `recommend_waiver_pickup` |
| Dynasty decisions account for future value | ✅ | `league/trade.py::age_curve_multiplier` (disclosed heuristic, not trained — D25) |

## Agent/orchestrator

| Criterion | Status | Where |
|---|---|---|
| Orchestrator can decompose work | ✅ | `agents/orchestrator.py::run_pipeline`, topological readiness batches |
| Agents have explicit responsibilities | ✅ | `agents/registry.py::AGENT_REGISTRY`, 9 named agents |
| Structured task/result contracts exist | ✅ | `agents/contracts.py` mirrors `AGENT_CONTRACTS.md` |
| Dependencies are explicit | ✅ | `Task.depends_on` |
| Independent tasks can run in parallel | ✅ | `ThreadPoolExecutor`; `tests/unit/test_agents.py::test_independent_tasks_run_concurrently` (timing-based) |
| Provenance is preserved across agent outputs | ✅ | `Result` contract fields |
| Critique/review can be invoked | ✅ | `run_evaluation_qa` agent |
| Agent disagreements are explicitly resolved | ✅ | `agents/disagreement.py`, both majority and minority positions preserved |
| Evaluation/QA can reject unsupported claims | ✅ | `REJECT` task state, forces `UNVALIDATED` |
| Agent failures are retried/recovered or surfaced | ✅ | `MAX_RETRIES = 2`, `BACKOFF_SECONDS`, `FAILED` state |
| Shared project state exists | ✅ | `agent_tasks`/`agent_results`/`agent_disagreements` tables in the same DuckDB |
| Milestone state is persistent | ✅ | `milestones` table + `docs/PROJECT_STATE.md` |

## Engineering quality

| Criterion | Status | Where |
|---|---|---|
| CLAUDE.md contains durable project instructions | ✅ | `CLAUDE.md` |
| README documents setup and workflows | ✅ | `README.md` — rewritten in M13; the prior version only described the original planning package, not the built system (a real gap, fixed alongside the D28/D29 bug fixes) |
| Data/model/validation docs exist | ✅ | `docs/DATA_SOURCES.md`, `reports/*.md` |
| Tests run automatically/continuously | ✅ | `.github/workflows/ci.yml` — added in M13 (lint + offline test suite on push/PR to `main`); previously only local `make test`/`make lint` |
| Bugs discovered during implementation get regression tests | ✅ | every D-numbered bug in `docs/DECISIONS.md` (D24, D26, D28, D29) has a named regression test |
| Secrets are not committed | ✅ | M13 audit: `.gitignore` excludes `.env`/`.env.*`/`data/`/`models/`/`*.duckdb`; no hardcoded credential patterns in tracked source; `.env.example` files contain only placeholders |
| Ruff/static checks pass | ✅ | `make lint` clean as of the final M13 commit |
| Unit tests pass | ✅ | 204 passed offline (`make test`) |
| Integration tests pass where configured | ✅ | network-marked suite, run against real sources throughout the session (most recently the M13 simulation live test) |
| End-to-end workflow succeeds | ✅ | full pipeline (`ingest`→`identity`→`features`→`market`→`train`→`evaluate`→`edge`→`simulate`→`orchestrate`→`serve`) re-run end to end in M13 after the REG/POST fix |
| New season ingestion is documented and repeatable | ✅ | `README.md`'s pipeline section; every builder is an idempotent upsert, safe to re-run |
| Architecture review completed | ✅ | continuous per-milestone reviews (see every D-entry in `docs/DECISIONS.md`); M13 specifically found and fixed a cross-cutting data-correctness bug (D28) and two simulation-design bugs (D29) via exactly this kind of review |
| Requirements traceability review completed | ✅ | this document |

## Application/interface

| Criterion | Status | Where |
|---|---|---|
| The interface exposes the validated player intelligence | ✅ | `api/routers/*.py`, all reading already-persisted/validated tables |
| EDGE/evidence can be inspected | ✅ | `EdgeView.tsx`, `EvidenceView.tsx` |
| Rookie evaluation can be inspected | ✅ | `RookiesView.tsx` |
| League context can be loaded | ✅ | `LeagueView.tsx`, `/league/{id}/context` |
| Roster-aware recommendations can be generated | ✅ | league draft/waiver forms in `LeagueView.tsx` |
| Draft/waiver/FAAB recommendations can be generated | ✅ | same |
| Recommendation explanations show relevant evidence/provenance | ✅ | reasons rendered alongside every recommendation |
| UI does not duplicate or bypass core model/decision logic | ✅ | D27; every API field traces to a persisted table or a direct M10 function call — verified literally by killing the API process and confirming the UI breaks rather than serving stale data |

## Completion standard

Every criterion above is either ✅ MET (backed by real data, a passing test, and — for
data/market/evidence items — a documented real-environment constraint) or explicitly ⚠️
LIMITED/❌ BLOCKED with its reason and fallback named inline and cross-referenced to the
`docs/DECISIONS.md` entry that first established it. Nothing here is marked done because a
demo ran; every ✅ traces to a specific module, a specific test, and — where the criterion is
about a real-world claim (baselines beaten, EDGE profitable, calibration achieved,
correlation positive) — a specific report or live-verified number.
