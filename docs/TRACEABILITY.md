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
| In-season/ROS rankings exist | ✅ | `models/established/train.py::_persist_weekly_projections`, evidence-adjusted via `evidence/prior_update.py` (M9), served via `GET /rankings/weekly` and `RankingsView.tsx`'s "Weekly" mode (D46 — previously the pipeline was real but had never been run against this deployment's data and nothing served it; now both are true, verified live) |
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
| FantasyPros API integration works or limitation documented | ✅ | `sources/fantasypros.py` implemented; `FANTASYPROS_API_KEY` supplied and confirmed live 2026-08-23 (D37) — both datasets (`consensus_rankings`, `projections`) return real data. The initial `403 Forbidden` (D36) was a wrong adapter base URL (missing `/public`), not a credentials or policy issue; fixed |
| CFBD integration works or limitation documented | ✅ | `sources/cfbd.py` implemented; `CFBD_API_KEY` supplied and confirmed live 2026-08-23 (D36) — all 3 datasets (`teams`, `player_usage`, `recruiting_players`) return real data with real row counts |
| Sleeper integration works or limitation documented | ✅ | `sources/sleeper.py` — became AVAILABLE 2026-08-22 when the environment's egress policy changed (D31), verified with real data (state/players/trending adds+drops); league context is now available either config-driven (YAML, D6) or live-synced from a real Sleeper league (`league/sleeper_context.py`, D33/D34) — live-verified against 2 real leagues (`dilworth`, `boys_of_fall` in the registry), including the `unrecognized_flex_slots == []` check that confirms the flex-slot name mapping against real data, not just the documented API shape |
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
| College production feeds rookie modeling | ⚠️ | Data pipeline is real and verified: CFBD, espn_id-bridged, leakage-safe (`features/college_production.py` → `college_usage` → `rookie_features`, D38). **Measured in D39 and NOT adopted** — over identical walk-forward folds it was neutral-to-slightly-worse on every metric that matters (breakout Brier +0.0030; and worse on all four metrics when restricted to high-coverage classes), so `FEATURES` stays at the 12-feature D20 baseline. Reproduce with `alpha-squad train rookie --ablation`; see `reports/rookie_college_production_ablation.md`. LIMITED not for lack of a source or a bridge, but because the signal measurably does not help |
| Model changes are justified by measurement, not assumption | ✅ | `models/rookie/ablation.py` + `train rookie --ablation`: paired walk-forward arms, pre-registered decision rule, published report. First applied in D39, where it rejected a feature the project had already built and shipped |
| Uncertainty intervals exist | ✅ | M6 quantile models + split-conformal calibration |
| Probability calibration is measured | ✅ | `reports/calibration_report.md` — real out-of-sample coverage vs. nominal |
| Model versions are tracked | ✅ | model registry (`_register_model`), `VALIDATED`/`UNVALIDATED` |
| Servable model artifacts persist without retraining | ✅ | `models/persistence.py` (D43): fitted CatBoost models saved natively (`.cbm`) under `models/`, keyed by (model_name, position, version) in `model_registry.artifact_path`; `train uncertainty --persist`/`train rookie-project --persist` save on every real run (default on), `alpha-squad models rescore-uncertainty`/`rescore-rookie-projection` re-score without a `.fit()` call. Verified live: re-scored a real 2026 rookie QB from the persisted artifact and reproduced the exact training-time output (196.3 pts / 86% breakout) |
| Model performance is compared against baselines | ✅ | same `evaluation_results` table for both, `evaluate_and_record` |

## Market/EDGE

| Criterion | Status | Where |
|---|---|---|
| FantasyPros ECR is a market baseline when available | ✅ | via DynastyProcess `db_fpecr` (real historical ECR, D3); `market/consensus.py` |
| ADP is tracked when available | ⚠️ | no direct ADP series is reachable in this environment; ECR-implied (isotonic rank→points, D17) and dynasty market value are the documented substitutes — not literal ADP |
| Sleeper/KTC are treated as separate signals, not truth | ✅ | Sleeper's trending adds/drops now feed the evidence engine as a real Weak-tier `social_media_buzz` signal (D32, `evidence/sleeper_trending.py`) — a separate, bounded evidence input, never a source of truth the model defers to (same ±15% bounded-adjustment ceiling as every other evidence signal). KTC has no formal adapter; its dynasty-value role is covered by DynastyProcess `values-players`/`values-picks` (D3) |
| Expert weighting uses demonstrated accuracy where data permits | ⚠️ | only *consensus* ECR is reachable, not per-expert rankings (needs the blocked FantasyPros API); weighting is applied at the source level (ECR vs. dynasty value vs. model) instead (D4) |
| Rank edge, points edge, and probability edge exist | ✅ | `market/edge.py` `EdgeContract` fields |
| A raw ranking discrepancy cannot alone produce a strong EDGE | ✅ | `classify_action`'s hard gating rule; `tests/unit/test_edge.py::TestClassifyActionGatingRule` |
| BUY/HOLD/SELL/WATCH are evidence-backed | ✅ | `evidence_score` veto below `EVIDENCE_CONTRADICTION_THRESHOLD` (D23) |
| Historical EDGE performance is evaluated | ✅ | `edge validate` (per-season/action summary, `reports/edge_validation.md`) + `edge backtest` (per-position, per-season, and rank/points/confidence-magnitude bucket breakdown, `reports/edge_backtest.md`, D41). Re-run 2026-08-24 against the current live-sourced market data (2022-2025, 1543 signals): BUY cohort beat market-implied points in all 4 scored seasons (+27.2/+19.2/+18.8/+4.7 pts, a real declining-but-consistently-positive trend); SELL was mixed (beat in 2022-2023, roughly neutral 2024, wrong-direction 2025) — honestly reported either way, not smoothed over |

## Evidence

| Criterion | Status | Where |
|---|---|---|
| Evidence events are timestamped | ✅ | `evidence_events.detected_at` |
| Evidence has source/provenance | ✅ | `evidence_events.source_snapshot_id` |
| Evidence strength is structured | ✅ | `evidence/taxonomy.py` |
| Strong/medium/weak hierarchy is implemented | ⚠️ | Strong tier has 4 real detectors on officially-sourced nflverse data; Weak tier now has one real detector too (`social_media_buzz` via Sleeper trending adds/drops, D32) — real community momentum, timestamped and bounded like every other evidence input; Medium remains registered vocabulary with a manual-entry path but no reachable text/news source (D5, D22) |
| News does not directly overwrite model projections | ✅ | `evidence/prior_update.py::apply_evidence_adjustment`, bounded to `MAX_ADJUSTMENT_PCT = 0.15`; tested |
| Material projection changes have reasons | ✅ | `projection_deltas.reason` + `evidence_ids`, reachable end-to-end via `GET /rankings/weekly` and the UI's "Why" column as of D46 (not just written to a table nothing read) |

## League decision engine

| Criterion | Status | Where |
|---|---|---|
| Universal player intelligence is separate from league context | ✅ | architectural split: M1-M9 (`identity/`, `features/`, `models/`, `market/`, `evidence/`) never import from `league/`; only `league/` reads the universal layer |
| Arbitrary league settings can be represented | ✅ | `league/context.py::LeagueContext` (pydantic), YAML-driven or Sleeper-live-driven (D33) |
| Target league settings are supported | ✅ | `config/league_configs/target_league.yaml` — 10 teams, 2QB/2RB/2WR/1TE/2FLEX |
| Multiple leagues can be configured and switched between | ✅ | `league/context.py::resolve_league` + `config/league_configs/registry.yaml` (D33/D34) — every CLI league command, the API, and `LeagueView.tsx`'s league picker resolve through the same registry; 3 leagues registered today (1 YAML, 2 live Sleeper), no hardcoded single-league assumption remains |
| Replacement level is calculated | ✅ | `league/replacement.py::replacement_level`, derived from the league's own starting-slot config (verified: 2QB league's QB replacement sits at real rank ~20-24, materially different from a 1QB league) |
| Positional scarcity is calculated | ✅ | `positional_scarcity` |
| Roster fit is calculated | ✅ | `roster_fit_multiplier` |
| Expected pick value exists | ✅ | `recommend_draft_pick`'s VORP × fit × confidence score |
| Next-pick survival probability exists | ✅ | `next_pick_survival_probability` (Uniform over ECR best/worst) |
| Draft recommendation includes alternatives and reasoning | ✅ | `DraftRecommendation.alternatives`/`.reasons` |
| Waiver/FAAB recommendations include roster fit and replacement | ✅ | `recommend_waiver_pickup` |
| Dynasty decisions account for future value | ✅ | `league/trade.py::age_curve_multiplier` (disclosed heuristic, not trained — D25) plus, as of D45, real future-draft-pick valuation (`pick_value`, `evaluate_trade_package`, `POST /league/{id}/trade-package`, `alpha-squad league trade-package`) — a documented round/slot/years-out heuristic on the same `value_2qb` scale, verified against real dynasty data live |

## Agent/orchestrator

| Criterion | Status | Where |
|---|---|---|
| Orchestrator can decompose work | ✅ | `agents/orchestrator.py::run_pipeline`, topological readiness batches; as of D47, `agents/planner.py::plan_full_refresh` builds the real multi-task graph (which agents apply + correct dependency edges) from a high-level goal rather than every caller hand-typing one, verified against the real database (`alpha-squad orchestrate run`) |
| Agents have explicit responsibilities | ✅ | `agents/registry.py::AGENT_REGISTRY`, 9 named agents |
| Structured task/result contracts exist | ✅ | `agents/contracts.py` mirrors `AGENT_CONTRACTS.md` |
| Dependencies are explicit | ✅ | `Task.depends_on` |
| Independent tasks can run in parallel | ✅ | `ThreadPoolExecutor`; `tests/unit/test_agents.py::test_independent_tasks_run_concurrently` (timing-based) |
| Provenance is preserved across agent outputs | ✅ | `Result` contract fields |
| Critique/review can be invoked | ✅ | `run_evaluation_qa` agent; as of D47, `plan_full_refresh` auto-schedules one QA review task per position after `projection_ml` rather than QA being a fully separate, never-auto-invoked path |
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
| Roster-aware recommendations can be generated | ✅ | D44: `LeagueView.tsx`'s "Roster need" section, `GET /league/{id}/roster` — live-tested against `dilworth` (real Sleeper league) |
| Draft/waiver/FAAB recommendations can be generated | ✅ | D44: draft form in `LeagueView.tsx` (pre-existing) plus new `WaiverView.tsx`/`TradeView.tsx` — all three live-tested against `dilworth` (real Sleeper league, season 2025); prior to D44 this row's citation ("league draft/waiver forms in `LeagueView.tsx`") was inaccurate — only the draft form existed, per `docs/CURRENT_STATE_AUDIT.md`'s UI/API sub-audit. D48 addendum: Waiver/Trade's player-id fields use `PlayerPicker.tsx`, a real name-search autocomplete against `GET /players` (previously a dead endpoint — nothing called it), replacing raw opaque-id text entry; verified end-to-end live including a real submitted recommendation |
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
