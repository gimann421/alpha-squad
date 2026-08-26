# Alpha Squad — Current-State Audit

**Audit date:** 2026-08-24
**Audited commit:** `e0ca6c3` on `claude/alpha-squad-plan-qhpg3r` (working tree clean at audit start)
**Method:** Direct inspection of source, tests, config, docs, and Git/DB state; direct execution of
the test suite, linters, baseline evaluation, established-ML training, and live-network league/
Sleeper tests; four parallel adversarial sub-audits (agent/orchestrator, evidence/EDGE, UI/API,
league decision engine) each required to cite file:line and re-run tests rather than trust
docstrings. This is an audit only — no implementation changes were made to produce it.

---

## 1–2. Scope and authoritative requirements

Read in full: `CLAUDE.md`, `PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`,
`ACCEPTANCE_CRITERIA.md`, `AGENT_CONTRACTS.md`, `CLAUDE_CODE_LEAD_PROMPT.md`. No material
contradictions between them; `CLAUDE_CODE_LEAD_PROMPT.md` is a more verbose restatement of the same
requirements. `CLAUDE.md`'s data-source-status note originally said direct Sleeper/FantasyPros/CFBD
calls were blocked by egress policy — false as of D36/D37, both confirmed reachable and
live-tested (see §8, §22) — **RESOLVED (D50):** the note has been rewritten to match current
reality.

## 3. Status definitions used below

Capability status (6-value): **FULLY IMPLEMENTED AND VERIFIED** (code exists, does what it claims,
verified by a passing test or a fresh direct run) · **IMPLEMENTED BUT NOT FULLY VERIFIED** (code
exists and looks correct but lacks a test or fresh run proving it) · **PARTIALLY IMPLEMENTED**
(some required sub-behavior missing) · **SCAFFOLDED / STUBBED** (interface/shape exists, logic
does not) · **BLOCKED BY EXTERNAL DEPENDENCY** · **NOT IMPLEMENTED**.

Requirements-coverage table (§5) uses ACCEPTANCE_CRITERIA.md's own vocabulary: **COMPLETE/VERIFIED
· IMPLEMENTED/UNVERIFIED · PARTIAL · STUB · BLOCKED · NOT IMPLEMENTED**.

---

## 4. Executive summary

*(Refreshed after a P0-P2/P4/P5/P7/P8 hardening pass, D41-D48 in `docs/DECISIONS.md` — the
sections below retain their original text as a historical record where a gap they described has
since closed, with an inline note pointing to the D-number that closed it, per this document's
own standard of correcting rather than silently rewriting a prior finding.)*

Alpha Squad is a genuinely substantial, mostly-real system, not a demo wearing a spec's clothing.
The data layer, canonical identity, leakage-safe historical features, established-player ML
(CatBoost beats every baseline, verified with fresh numbers), uncertainty/calibration, rookie
modeling, market/EDGE (with a real, current backtest artifact — D41), evidence detection (now
genuinely reaching a served ranking, not just logged — D46), and the league decision engine
(verified live against a real Sleeper league, including real future-pick trade valuation — D45)
are all real, tested, and do what the docs claim. Engineering hygiene is healthy and improved
since the original audit: 301/301 offline tests pass (up from 259), lint/format are clean, a CI
guardrail now blocks a repeat of the D35 credential leak (D42), leakage tests are adversarially
designed and pass, and no name-based joins exist anywhere in `src/`.

The three weaknesses this section originally led with are now closed, each with live verification,
not just code review:
1. ~~No model artifact is ever persisted to disk~~ **CLOSED (D43).** `models/persistence.py`
   gives the two paths that actually serve live predictions (uncertainty → `/rankings`, rookie
   projection → `/rookies`) a real inference-only path — verified by re-scoring a real player from
   a saved artifact and reproducing the exact training-time output with no `.fit()` call.
2. ~~The orchestrator has no real task decomposition~~ **CLOSED (D47).** `agents/planner.py`
   builds the real multi-stage task graph (agent selection + correct dependency edges, read off
   what each agent's code actually queries/writes) from a high-level goal — verified against the
   real database with genuine cross-stage concurrency and correct ordering, not just unit tests.
3. ~~Waiver/trade/roster-need are invisible in the app~~ **CLOSED (D44).** All three wired into
   the SPA and live-verified against a real Sleeper league; draft, waiver, trade, and roster-need
   are all reachable today. A dead-code check during the same hardening pass also found (and
   fixed, D48) that a real name-search endpoint (`GET /players`) existed but nothing called it —
   Waiver/Trade's player fields used raw opaque-id text entry until this pass added a real search
   picker, which itself surfaced and fixed a genuine label-click-forwarding bug in the process.

4. ~~The Monte Carlo team-season simulator has no API endpoint and is CLI-only~~ **CLOSED (D49).**
   `POST /simulate/team-season` + `SimulationView.tsx`, live-verified with a real KC 2025 run.
   Closing this also surfaced and fixed a real, separate gap: `team_week_points` was empty in
   this deployment because `build_team_week_points` had never been wired to a CLI command — added
   `alpha-squad features build-team-scores` and ran it for real. This was the last of the four
   "built but invisible" capabilities (waiver/trade/roster-need/simulation) identified at the
   start of this hardening pass.

What remains open: the one item this audit explicitly cannot close on its own — real API keys
from the D35 leak remain permanently retrievable from Git history. That decision was already made
by the user at the time (D35: offered a full history rewrite, explicitly declined it) — this
session added a CI guardrail against a repeat (D42) rather than reopening a decision that was
already made, since an autonomous session has no standing to perform a destructive,
irreversible, shared-history rewrite on its own initiative regardless.

Nothing here is fabricated data, and no primary time-series split violates the walk-forward rule —
the project's stated non-negotiables hold throughout this hardening pass too. The gap between "the
pipeline can prove CatBoost beats a baseline" and "a user can open the app and get a trustworthy,
personalized decision for their real league" — the framing this audit opened with — has closed
substantially: draft, waiver, trade, roster-need, and now simulation are all real, live-verified,
and reachable from the app; evidence genuinely reaches a served ranking; EDGE has a real,
reviewable backtest; dynasty trades account for future picks; and the orchestrator can build its
own task graph. What's left is narrower and mostly disclosed rather than discovered fresh: the
D35 credential exposure (a decision, not a code fix), and the lower-value P2/P3 items in
`docs/IMPLEMENTATION_GAP_ANALYSIS.md`.

## 5. Requirements coverage (ACCEPTANCE_CRITERIA.md, line-by-line)

### Product completeness
| Item | Status | Evidence |
|---|---|---|
| Redraft preseason projections/rankings | COMPLETE/VERIFIED | `/rankings` API + UI; established ML trained and evaluated this session |
| Dynasty rookie rankings | COMPLETE/VERIFIED | `/rookies`; rookie model trained, D40-fixed to project the unplayed 2026 class |
| Dynasty overall rankings | COMPLETE/VERIFIED | `dynasty_values` (DynastyProcess `values-players`), served via league/trade paths |
| In-season/ROS rankings | PARTIAL | Established model supports season-level projection; no explicit in-season/ROS re-projection loop verified this run |
| Projection ranges and probabilities | COMPLETE/VERIFIED | `reports/calibration_report.md`: real out-of-sample p10/p90 coverage, 0.657–0.870 range vs 0.80 target |
| EDGE scores | COMPLETE/VERIFIED | `market/edge.py::classify_action`, gated (see §15), regression-tested |
| Evidence/provenance explains material outliers | COMPLETE/VERIFIED | D46: `GET /rankings/weekly` + `RankingsView.tsx`'s "Weekly" mode surfaces real evidence-adjusted values with reasons, verified live in a real browser |
| League-specific recommendations | COMPLETE/VERIFIED | Draft/waiver/trade all verified live against a real Sleeper league this session (§17–18) |
| Draft decisions | COMPLETE/VERIFIED | `draft.py::recommend_draft_pick`, live-tested |
| Waiver/FAAB decisions | COMPLETE/VERIFIED | `waiver.py`, live-tested; D44 wired it into `WaiverView.tsx` and recorded real `waiver_bid` decisions from the UI (previously zero) |
| Roster-aware decisions | COMPLETE/VERIFIED | Roster-fit math is real; D44 added a UI surface (`LeagueView.tsx`'s "Roster need" section) that calls it (§20) |
| Recommendation changes are explainable | COMPLETE/VERIFIED | `reasons` lists exist on draft/waiver/trade/EDGE outputs (D44 confirmed rendered in the UI); D46 adds the dedicated "what changed and why" view for weekly projections specifically (`RankingsView.tsx`'s "Weekly" mode), verified live |

### Data
| Item | Status | Evidence |
|---|---|---|
| nflverse ingestion works | COMPLETE/VERIFIED | Primary path, run this session |
| FantasyPros API integration works | COMPLETE/VERIFIED | D37 fixed base URL; confirmed reachable and live |
| CFBD integration works | COMPLETE/VERIFIED | D38; real `player_usage` coverage back to 2014 |
| Sleeper integration works | COMPLETE/VERIFIED | Live-tested this session against 2 real leagues |
| Official/current evidence workflow exists | IMPLEMENTED/UNVERIFIED | 5 detectors real (§16); "official/current" breadth not independently re-verified this run |
| Raw/source snapshots preserved | COMPLETE/VERIFIED | `snapshot_registry`, `data/raw/` Parquet |
| Canonical player IDs exist | COMPLETE/VERIFIED | Deterministic `asq_<md5(gsis_id)>` scheme |
| Ambiguous mappings are quarantined | COMPLETE/VERIFIED | `identity_exceptions` queue |
| No production joins depend on names alone | COMPLETE/VERIFIED | Independently re-verified this run with a broader grep across all of `src/`, not just `identity/`; zero name-joins found |
| Data quality checks fail loudly | IMPLEMENTED/UNVERIFIED | `require_snapshot` raises on missing snapshot; no dedicated "fail-loudly" test suite reviewed this run |
| API/source failures never fabricate success | COMPLETE/VERIFIED | `SourceBlockedError`→`BLOCKED_BY_POLICY`; UI/API agent confirmed no fake-data fallback anywhere |

### Historical integrity
| Item | Status | Evidence |
|---|---|---|
| Historical predictions reconstructable as-of a date | IMPLEMENTED/UNVERIFIED | Snapshot IDs threaded through most tables; no artifact exists to "reconstruct" a *served* prediction (no model persistence, §11/§24) |
| Every time-sensitive input has captured/effective timestamps | COMPLETE/VERIFIED | `source_snapshot_id`/`feature_version` pattern is consistent |
| Primary evaluation uses walk-forward validation | COMPLETE/VERIFIED | Confirmed by direct re-run this session (`reports/baseline_evaluation.md`, `reports/established_ml_evaluation.md`) |
| No leakage from future injuries/final ADP/EOS depth charts/target outcomes | COMPLETE/VERIFIED | `tests/leakage/` adversarial suite passing (8/8) |
| Leakage tests exist and pass | COMPLETE/VERIFIED | Verified directly this run |

### Modeling
| Item | Status | Evidence |
|---|---|---|
| Simple baselines exist | COMPLETE/VERIFIED | Re-run this session, real numbers in `reports/baseline_evaluation.md` |
| Position-specific established models exist | COMPLETE/VERIFIED | Trained this session for QB/RB/WR/TE |
| CatBoost exists | COMPLETE/VERIFIED | Trained, beats baselines at all 4 positions 2021–2025 |
| XGBoost challenger exists or rejected with evidence | COMPLETE/VERIFIED | Present in `established_ml_evaluation.md` alongside CatBoost/Ridge |
| Opportunity modeling exists | IMPLEMENTED/UNVERIFIED | ffopportunity wired per docs; not independently re-verified this run |
| Team environment modeling exists | COMPLETE/VERIFIED | `features/team.py`, `team_week_stats`, also consumed by simulation module |
| Rookie model separate from established model | COMPLETE/VERIFIED | Distinct pipeline, distinct feature set, distinct code path |
| Rookie breakout probability exists | COMPLETE/VERIFIED | `breakout_probability` / `breakout_top24` classifier |
| Draft capital is explicit | COMPLETE/VERIFIED | D40 fixed the 2026-class draft-capital gap (esb_id join) |
| Uncertainty intervals exist | COMPLETE/VERIFIED | p10/p25/median/p75/p90, independent training path |
| Probability calibration is measured | COMPLETE/VERIFIED | `reports/calibration_report.md`, real coverage numbers including a real miss (QB 2022, 0.657) |
| Model versions are tracked | COMPLETE/VERIFIED | `model_registry`, `feature_version`/`model_version` columns |
| Model performance compared against baselines | COMPLETE/VERIFIED | Same shared `evaluation_results` table, same report |

### Market/EDGE
| Item | Status | Evidence |
|---|---|---|
| FantasyPros ECR is a market baseline | COMPLETE/VERIFIED | Dual-sourced: DynastyProcess historical mirror + live FantasyPros series |
| ADP tracked when available | IMPLEMENTED/UNVERIFIED | Present in schema; not independently re-verified this run |
| Sleeper/KTC treated as separate signals, not truth | COMPLETE/VERIFIED | `source` column on `market_snapshot`; DynastyProcess substitutes KTC's dynasty-value role explicitly, not blended silently |
| Expert weighting uses demonstrated accuracy where data permits | LIMITED (empirically confirmed, D51) | Real per-expert identity is unavailable even from the live paid FantasyPros API (confirmed via a real call, not assumed); the coarser proxy (`ecr_best`/`ecr_worst` dispersion) was measured against 1,925 real player-seasons and found no consistent relationship with market accuracy — not adopted |
| Rank edge, points edge, probability edge exist | COMPLETE/VERIFIED | `edge.py`; probability edge via uncertainty model's `top24_prob` |
| Raw ranking discrepancy alone cannot produce a strong EDGE | COMPLETE/VERIFIED | `classify_action` requires rank AND points edge to agree, above threshold, plus confidence floor and evidence non-veto — regression-tested |
| BUY/HOLD/SELL/WATCH are evidence-backed | COMPLETE/VERIFIED (gate exists) / PARTIAL (usually neutral in practice) | Evidence-veto gate real; per EDGE sub-audit, the veto is rarely the deciding factor in practice since evidence coverage is sparse |
| Historical EDGE performance is evaluated | PARTIAL | A historical backtest was run (per EDGE sub-audit) with genuine mixed results, but **no committed report artifact exists** — confirmed this run: `reports/` has no edge/backtest file |

### Evidence
| Item | Status | Evidence |
|---|---|---|
| Evidence events are timestamped | COMPLETE/VERIFIED | `evidence_events` schema |
| Evidence has source/provenance | COMPLETE/VERIFIED | Source field per detector |
| Evidence strength is structured | COMPLETE/VERIFIED | Strong/Medium/Weak tiers implemented |
| Strong/medium/weak hierarchy implemented | COMPLETE/VERIFIED | 4 Strong-tier detectors (depth-chart, injury, roster transaction, usage-share shift) + 1 Weak-tier (Sleeper trending) |
| News does not directly overwrite model projections | COMPLETE/VERIFIED | Bounded (±15%) evidence-adjustment is a separate, disclosed adjustment, not a projection overwrite |
| Material projection changes have reasons | COMPLETE/VERIFIED | D46: the bounded evidence-adjusted-projection logic now feeds `GET /rankings/weekly`, the actually-served weekly ranking, not just EDGE's veto gate — verified live with real reasons rendered |

### League decision engine
| Item | Status | Evidence |
|---|---|---|
| Universal player intelligence separate from league context | COMPLETE/VERIFIED | Confirmed by league sub-audit: zero `.fit()`/`.train()` calls anywhere in `src/alpha_squad/league/`; all league functions are pure reads over universal outputs |
| Arbitrary league settings can be represented | COMPLETE/VERIFIED | `LeagueContext` schema + `registry.yaml` supports both static YAML and live Sleeper hydration |
| Target league settings supported (10 teams, 2QB/2RB/2WR/1TE/2FLEX) | COMPLETE/VERIFIED | `target_league.yaml`; `FLEX_ELIGIBILITY` mapping confirmed correct against 2 real Sleeper leagues (D34) |
| Replacement level is calculated | COMPLETE/VERIFIED | `replacement.py`; proven to differ materially between 1QB/2QB configs, both synthetically and on real 2025 data |
| Positional scarcity is calculated | COMPLETE/VERIFIED | Same VBD mechanism |
| Roster fit is calculated | COMPLETE/VERIFIED | `roster.py::roster_need`/`roster_fit_multiplier`, driven by the calling team's actual roster |
| Expected pick value exists | COMPLETE/VERIFIED | VORP × fit × risk × survival composite in `draft.py` |
| Next-pick survival probability exists | COMPLETE/VERIFIED | Real uniform-CDF model over `market_snapshot.ecr_best/ecr_worst` dispersion, not a placeholder |
| Draft recommendation includes alternatives and reasoning | COMPLETE/VERIFIED | `top[1:]` + per-candidate `reasons` |
| Waiver/FAAB recommendations include roster fit and replacement | COMPLETE/VERIFIED | All 8 PRODUCT_SPEC.md sub-factors present in `waiver.py`, live-tested |
| Dynasty decisions account for future value | COMPLETE/VERIFIED | D45 closed this: `pick_value`/`evaluate_trade_package` (real round/slot/years-out heuristic on the `value_2qb` scale) + `POST /league/{id}/trade-package`. Verified live. `LeagueContext.future_picks` itself remains intentionally unread — confirmed always empty in this deployment (no traded-picks data source), so pick assets are explicit caller input instead, per D45 |

### Agent/orchestrator
| Item | Status | Evidence |
|---|---|---|
| Orchestrator can decompose work | COMPLETE/VERIFIED | D47: `agents/planner.py::plan_full_refresh` builds the real multi-stage task graph (agent selection + correct dependency edges) from a high-level goal instead of every caller hand-typing one; verified live against the real database with genuine `rookie_ml`/`projection_ml` concurrency and correct `market_edge` ordering |
| Agents have explicit responsibilities | COMPLETE/VERIFIED | All 9 required agents + optional `research_validation` exist in `registry.py` with one clear ownership each |
| Structured task/result contracts exist | COMPLETE/VERIFIED | `contracts.py`, matches AGENT_CONTRACTS.md shapes |
| Dependencies are explicit | COMPLETE/VERIFIED | Declared per-task, resolved by the orchestrator |
| Independent tasks can run in parallel | COMPLETE/VERIFIED | Real `ThreadPoolExecutor`-based concurrency, confirmed by the orchestrator sub-audit |
| Provenance preserved across agent outputs | COMPLETE/VERIFIED | Version fields threaded through `Result` objects |
| Critique/review can be invoked | IMPLEMENTED/UNVERIFIED | `evaluation_qa` agent exists; whether it substantively "rejects unsupported claims" beyond running existing test/validation functions was not independently re-verified with a live example this run |
| Agent disagreements are explicitly resolved | COMPLETE/VERIFIED | Real SQL-based detector in `disagreement.py` comparing independently-computed model vs. market values, not synthetic |
| Evaluation/QA can reject unsupported claims | IMPLEMENTED/UNVERIFIED | Same caveat as "critique/review" above |
| Agent failures are retried/recovered or surfaced | COMPLETE/VERIFIED | Real retry-with-backoff in `orchestrator.py` |
| Shared project state exists | COMPLETE/VERIFIED | `agent_tasks`/`agent_results` DuckDB tables |
| Milestone state is persistent | COMPLETE/VERIFIED | `milestones` table, DB-locked writes |

### Engineering quality
| Item | Status | Evidence |
|---|---|---|
| CLAUDE.md contains durable project instructions | COMPLETE/VERIFIED | Present and current (D50 fixed the one stale note, §1) |
| README documents setup and workflows | IMPLEMENTED/UNVERIFIED | Present; not line-by-line verified against current CLI this run |
| Data/model/validation docs exist | COMPLETE/VERIFIED | `docs/DATA_SOURCES.md`, `docs/DECISIONS.md`, `docs/PROJECT_STATE.md`, `docs/TRACEABILITY.md` |
| Tests run automatically/continuously | COMPLETE/VERIFIED | `.github/workflows/ci.yml` runs `make lint && make test` on push/PR |
| Bugs discovered during implementation get regression tests | COMPLETE/VERIFIED | Pattern held throughout D36–D40 per `docs/DECISIONS.md` |
| Secrets are not committed | **PARTIAL — historical exposure** | Current tree clean; **real leaked API key values from the D35 incident remain permanently retrievable from Git history** (§23) |
| Ruff/static checks pass | COMPLETE/VERIFIED | Re-run this session: clean |
| Unit tests pass | COMPLETE/VERIFIED | 259/259, re-run this session |
| Integration tests pass where configured | COMPLETE/VERIFIED | Live network suite re-run this session: 6/6 passing against real Sleeper leagues |
| End-to-end workflow succeeds | IMPLEMENTED/UNVERIFIED | Individual stages verified this session; a single unbroken ingest→identity→features→train→serve run was not re-executed end-to-end in this audit turn |
| New season ingestion is documented and repeatable | IMPLEMENTED/UNVERIFIED | `Makefile` targets exist; not re-verified against a genuinely new season this run |
| Architecture review completed | COMPLETE/VERIFIED | This document, §6 |
| Requirements traceability review completed | COMPLETE/VERIFIED | This document, §5, plus `docs/TRACEABILITY.md` |

### Application/interface
| Item | Status | Evidence |
|---|---|---|
| Interface exposes the validated player intelligence | COMPLETE/VERIFIED | 8-tab SPA (D44 added Waiver/Trade), thin projection over API, no logic duplication (UI/API sub-audit) |
| EDGE/evidence can be inspected | COMPLETE/VERIFIED | EDGE and Evidence tabs |
| Rookie evaluation can be inspected | COMPLETE/VERIFIED | Rookies tab, incl. real historical comps on click |
| League context can be loaded | COMPLETE/VERIFIED | League tab, live-tested against real Sleeper league |
| Roster-aware recommendations can be generated | COMPLETE/VERIFIED | D44: `LeagueView.tsx`'s "Roster need" section calls `GET /league/{id}/roster` and renders the real `need` map; live-tested against `dilworth` (real Sleeper league) |
| Draft/waiver/FAAB recommendations can be generated | COMPLETE/VERIFIED | D44: `WaiverView.tsx` (new) and `TradeView.tsx` (new) now wire `postWaiver`/`postTrade` into reachable tabs, alongside the pre-existing draft form; all three live-tested against `dilworth` (real Sleeper league, season 2025) with real recommendations and reasons rendered |
| Recommendation explanations show relevant evidence/provenance | IMPLEMENTED/UNVERIFIED | D44 newly confirms `reasons` renders in all three league-decision views (draft, waiver, trade); still not independently re-confirmed for every other view (Rankings/EDGE/Evidence/Rookies) this session, so the broader status is left as-is rather than overclaimed |
| UI does not duplicate or bypass core model/decision logic | COMPLETE/VERIFIED | Confirmed by UI/API sub-audit: clean thin-projection architecture |

---

## 6. Current architecture vs. ARCHITECTURE.md

The pipeline shape matches ARCHITECTURE.md's diagram closely: Data Sources → Ingestion/Snapshots →
Canonical Identity → Feature Store → {Projection ML, Rookie ML, Market} → Evidence → EDGE →
League Context → League Decisions → Application. Two real divergences:

1. **Storage layout.** ARCHITECTURE.md suggests `data/processed/`, `data/features/`,
   `data/snapshots/` as separate directories. The actual implementation uses DuckDB tables for
   everything except immutable raw snapshots (`data/raw/` Parquet). This is a reasonable, disclosed
   divergence — DuckDB tables *are* the processed/feature/snapshot layer — not a gap, but the doc
   should be updated to describe reality.
2. **No model-artifact persistence.** ARCHITECTURE.md's storage list includes `models/` as a real
   directory; in practice `models/` (and `predictions/`, `state/`) contain only `.gitkeep`. Every
   model is retrained in-process on every training/evaluation run — there is no `.cbm`/pickle/joblib
   file anywhere, and no code path that loads a frozen model. This is the single most significant
   undocumented-until-now architectural fact discovered this audit: the system has **no
   inference-only serving path**. Every prediction currently shown by the API is generated by a
   training run in the same process, not by loading a previously-fit model.

The agent/orchestrator layer (§19) is a real engineering addition beyond the base pipeline diagram —
ARCHITECTURE.md §6 describes it accurately as an engineering layer, and the implementation matches
that description reasonably well, short of real task decomposition (see §19).

## 7. Repository map

| Path | Purpose | Status |
|---|---|---|
| `src/alpha_squad/sources/` | Per-source adapters (nflverse, DynastyProcess, cfbfastR, ffopportunity, + blocked-by-policy-aware Sleeper/FantasyPros/CFBD/KTC/ESPN) | Real, tested, live-verified |
| `src/alpha_squad/identity/` | Canonical player ID, crosswalk, quarantine, no-name-join guarantee | Real, tested |
| `src/alpha_squad/features/` | Leakage-safe historical feature construction (player/team) | Real, adversarially tested |
| `src/alpha_squad/models/baselines/` | Previous-year / weighted-2yr / ECR-implied baselines | Real, re-run this session |
| `src/alpha_squad/models/established/` | Position-specific CatBoost/XGBoost/Ridge | Real, trained this session |
| `src/alpha_squad/models/uncertainty/` | Independent quantile/conformal-style model | Real, calibration-tested |
| `src/alpha_squad/models/rookie/` | Draft capital + combine + landing spot model, historical comps, unplayed-class projection path | Real, D40-fixed |
| `src/alpha_squad/models/simulation/` | Correlated team-season Monte Carlo | Real, tested (`tests/unit/test_simulation.py`, `tests/integration/test_simulation_live.py`), served via `POST /simulate/team-season` (D49) |
| `src/alpha_squad/market/` | Market snapshot, isotonic curve, EDGE classification | Real, gated, regression-tested |
| `src/alpha_squad/evidence/` | 5 evidence detectors, bounded adjustment logic | Real detectors; adjustment now feeds `GET /rankings/weekly` (D46), not just EDGE's veto gate |
| `src/alpha_squad/league/` | context/decisions/draft/replacement/trade/waiver | Real, live-verified against a real Sleeper league this session |
| `src/alpha_squad/agents/` | contracts/registry/orchestrator/disagreement/state | Real scheduler engineering; agents are thin pipeline wrappers |
| `src/alpha_squad/api/` | FastAPI routers per domain | Real, thin, no logic duplication |
| `web/` | React/Vite/TS SPA, 9 tabs | Real; D44 wired waiver/trade/roster-need, D49 wired simulation — every decision/intelligence capability is now reachable from the UI |
| `tests/{unit,leakage,contracts,integration,e2e}/` | 259 offline + 42 network-marked | All offline tests pass; leakage/contracts genuinely adversarial |
| `docs/` | DATA_SOURCES, DECISIONS (append-only), PROJECT_STATE, TRACEABILITY | Living, mostly current |
| `.github/workflows/ci.yml` | Lint + offline test on push/PR | Real, minimal (no network-marked tests, no deploy step) |

## 8. Data layer audit

nflverse, DynastyProcess, cfbfastR-data, ffopportunity: **FULLY IMPLEMENTED AND VERIFIED** (primary
path, re-run this session). Sleeper: **FULLY IMPLEMENTED AND VERIFIED** — live-tested this session
against 2 real leagues (6/6 live tests passing, 276.68s real network time). FantasyPros: **FULLY
IMPLEMENTED AND VERIFIED** — base-URL bug fixed D37, both keys confirmed available. CFBD: **FULLY
IMPLEMENTED AND VERIFIED** — real `player_usage` coverage confirmed back to 2014. KTC: **BLOCKED BY
EXTERNAL DEPENDENCY** (direct `keeptradecut.com` still blocked by environment egress policy per
CLAUDE.md; DynastyProcess `values-players`/`values-picks` substitutes its dynasty-value role, and
this substitution is explicit and disclosed, not silent). ESPN: **BLOCKED BY EXTERNAL DEPENDENCY**,
same policy, no substitute currently wired since nothing in PRODUCT_SPEC.md's core outputs
specifically requires it.

## 9. Player identity audit

Deterministic `asq_<16 hex md5(gsis_id)>` scheme, `player_id_map` crosswalk, `identity_exceptions`
quarantine for ambiguous mappings — **FULLY IMPLEMENTED AND VERIFIED**. Re-verified this run with an
independent, broader grep across all of `src/alpha_squad/` (not just `identity/`, which is all the
existing regression test covers): zero name-based joins found anywhere.

## 10. Historical/as-of system audit (skeptical)

`source_snapshot_id`/`feature_version`/`model_version` are threaded through most pipeline tables,
and the leakage test suite is genuinely adversarial (hand-seeded fixtures, explicit "poison future
data" tests, independent-Python recomputation checks — confirmed by direct reading, not assumed from
a docstring). The honest caveat: because no model artifact is ever persisted (§6), "reconstruct a
historical prediction as-of a date" is true only in the sense that the *inputs* to a training run can
be reconstructed from stored snapshots — there is no frozen prediction artifact to reconstruct and
compare against. This is a real gap against ARCHITECTURE.md §13's reproducibility requirement, not
just a theoretical one.

## 11. Feature engineering audit

Leakage-safety-by-construction via SQL window frames, confirmed by direct code reading and by the
adversarial leakage test suite passing (re-run this session, 8/8). No further gaps found beyond
what's already reflected in §5's Data/Historical-integrity rows.

## 12. Modeling audit (REAL vs PLACEHOLDER)

All four established-player model families (baselines, CatBoost, XGBoost, Ridge) are **REAL** — not
placeholders — confirmed by directly running training this session and inspecting real per-position/
per-season numbers (e.g. `ml_season_catboost_qb` 2020: n=57, MAE=67.681, Spearman=0.712,
top12=0.750). The rookie model (draft capital + combine + landing spot, "v1"/12-feature) is **REAL**.
The rejected 15-feature "+college" candidate is a **REAL, honestly-reported negative result** (D39
ablation) — not a placeholder pretending to be an improvement. The uncertainty/quantile model is
**REAL**, independently trained, calibration-measured with a genuine miss disclosed (QB 2022, 0.657
vs 0.80 target) rather than hidden. Opportunity/team-environment modeling exists per docs; not
independently re-verified with a fresh run this audit turn (IMPLEMENTED BUT NOT FULLY VERIFIED).

## 13. Model validation audit

Established-player evaluation was **not previously run against the live database this session**
before I ran it myself this audit turn — `model_registry` held only rookie-family entries beforehand.
I ran the real training/evaluation commands directly to establish ground truth. Result, freshly
computed: **CatBoost genuinely and consistently outperforms every baseline (previous-year,
weighted-2yr, ECR-implied) at all 4 skill positions over the 2021–2025 walk-forward window** — this
is a positive, load-bearing, freshly-verified finding, not carried over from stale prior claims.

## 14. Rookie/prospect system audit

Draft capital + combine + landing-spot baseline model: real, trained, evaluated. D38's
college-production candidate: real ablation methodology (paired walk-forward folds, pre-registered
decision rule per `models/rookie/ablation.py`, published `reports/rookie_college_production_ablation.md`),
honest null/negative result, correctly not adopted. The distinct unlabeled
`rookie_projection_features`/`project_rookie_class()` path for forecasting an *unplayed* draft class
was fixed this session (D40) to correctly project the incoming 2026 class instead of the already-played
2025 class — verified via the `/rookies` API and `RookiesView.tsx`, which now default to the newest
class the API actually has rather than a hardcoded year. Historical comps (`comps.py`) are real:
standardized draft-capital + combine nearest-neighbor search, correctly restricted to strictly
earlier draft classes (no leakage). No evaluation metrics are written for the unplayed-class
projection path, by design (there is no ground truth yet) — this is correct behavior, not a gap.

## 15. Market/EDGE audit

`classify_action` (`market/edge.py:192`) is real, non-trivial, well-gated logic: BUY/SELL requires
rank edge AND points edge to agree, both above threshold (`RANK_EDGE_THRESHOLD=15`,
`POINTS_EDGE_THRESHOLD=15.0`), a confidence floor (`CONFIDENCE_THRESHOLD=0.5`), and no contradicting
evidence (`EVIDENCE_CONTRADICTION_THRESHOLD=0.35`) — a raw rank discrepancy alone can never produce a
strong EDGE, and this specific invariant is regression-tested. A historical EDGE backtest was run
(per the EDGE sub-audit) with genuine mixed results, but **there is no committed report artifact** —
confirmed directly this run: `reports/` contains baseline/calibration/established-ML/rookie-ablation
reports only, no edge/backtest file. This is a real gap: PRODUCT_SPEC.md and ACCEPTANCE_CRITERIA.md
both require historical EDGE performance to be evaluated and documented, and right now that evidence
is not preserved anywhere a reader could check it. EDGE should **not** be called "validated" on the
strength of what's currently on disk.

## 16. Evidence/current-information audit

Real detectors: 4 Strong-tier (depth-chart change, injury, roster transaction, usage-share shift) + 1
Weak-tier (Sleeper trending). A real, bounded (±15%) evidence-adjusted-projection function exists and
is correctly implemented. **As of D46, it is consumed downstream**: `GET /rankings/weekly` serves the
evidence-adjusted weekly value (falling back to the unadjusted base for players with no evidence that
week), ordered by the adjusted value, with reasons — verified live in a real browser. The gap D46
closed was structural, not conceptual: the weekly pipeline this depends on (`weekly_projection_snapshot`)
had simply never been run against this deployment's data, so there was nothing for evidence to adjust
regardless of how correct the adjustment code was. EDGE's veto gate (`EVIDENCE_CONTRADICTION_THRESHOLD`)
remains a separate, still-usually-neutral-in-practice consumer (per the EDGE sub-audit) — that
finding stands; it's the *only* consumer that changed. **Conclusion: this system stores, computes,
and now genuinely serves evidence-adjusted output for the weekly/in-season projection path** — the
season-level preseason path (`/rankings`) remains unaffected by evidence, correctly, since evidence
detectors only ever produce in-season events (D23) and adjusting a preseason number with in-season
evidence would not be a coherent operation.

## 17. League context audit (target league: 10 teams, 2QB/2RB/2WR/1TE/2FLEX)

**FULLY IMPLEMENTED AND VERIFIED.** `registry.yaml` registers the synthetic `target_league` plus two
**real** Sleeper league IDs (`dilworth`, `boys_of_fall`). I ran the live Sleeper/league integration
suite myself this audit turn: `ALPHA_SQUAD_TEST_SLEEPER_LEAGUE_ID=1326428555382394880 uv run pytest
tests/integration/test_sleeper_league_context_live.py tests/integration/test_league_live.py -m
network` → **6 passed in 276.68s**, real network I/O against Sleeper's production API, including
draft/replacement/trade/waiver against real data. `FLEX_ELIGIBILITY` mapping is confirmed correct
against both real registered leagues (D34: `unrecognized_flex_slots == []`). Replacement level
(`replacement.py`) is proven to produce a materially different QB threshold for a 2QB league vs a 1QB
league, both synthetically (`tests/unit/test_league.py`) and on real 2025 data (`docs/PROJECT_STATE.md`:
"~220 pts QB replacement vs ~138–146 RB/WR/TE, 20 real dedicated QB starters on real 2025 data").

## 18. League-specific decision engine audit

**FULLY IMPLEMENTED AND VERIFIED for draft, waiver, and dynasty trade (D45).** Draft
recommendation (`draft.py::recommend_draft_pick`) genuinely combines VORP × a real roster-fit
multiplier (computed from the *calling team's actual current roster*, not a generic list) × model
confidence × a real next-pick survival probability (a uniform-CDF model over real stored ECR
dispersion, not a constant) — verbatim-cited by the sub-audit. Waiver (`waiver.py`) produces a real
FAAB dollar bid bounded by the league's real budget and incorporates all 8 sub-factors named in
PRODUCT_SPEC.md. Trade/dynasty (`trade.py`) uses real dynasty market value and a disclosed heuristic
age-curve, and — as of D45 — real future-draft-pick valuation via `pick_value`/
`evaluate_trade_package` (a documented round/slot/years-out heuristic anchored to the real
`value_2qb` scale, not fit from data since no real fantasy-rookie-draft-slot outcome dataset exists
here). `LeagueContext.future_picks` itself remains deliberately unread — it is always `{}` in this
deployment (no traded-picks data source), so D45 takes pick assets as explicit caller input
instead of silently doing nothing against an always-empty field. Universal/league separation is
genuinely respected: zero `.fit()`/`.train()` calls anywhere in `league/`. The soft spot is usage,
not implementation: only one decision (a single `draft_pick`) had ever been persisted in this
deployment's `decisions` table despite three decision types being fully built and live-verified —
now that the UI actually calls all three (D44), real `waiver_bid` and `dynasty_trade` decisions were
recorded for the first time this session (against a working copy of the database, not this
deployment's original `data/alpha_squad.duckdb`, since D44 ran in an isolated worktree with no prior
ingest of its own).

## 19. Agent/orchestrator audit

**Real engineering, not a real multi-agent system in the "autonomous planning agents" sense.** All 9
required agents (+ optional `research_validation`) exist in `registry.py` with clear ownership, but
each is a thin wrapper calling a pre-existing M1–M10 pipeline function (e.g. calling
`build_identity()`/`run_rookie_models()` directly) — there is no independent reasoning or planning
inside an agent. The orchestrator (`orchestrator.py`) is genuinely real: `ThreadPoolExecutor`-based
concurrent execution (confirmed independent tasks actually overlap in time, not just called in a
loop), real dependency-graph resolution, real retry-with-backoff, and real DB-locked persistent state
in `agent_tasks`/`agent_results`/`milestones` (reconstructable, not in-memory only). Disagreement
detection (`disagreement.py`) is real and non-synthetic: it compares independently-computed
model-prediction vs. market-rank values via SQL, not example data. **Task decomposition, previously
the honest weak point (the DAG shape was fixed/hand-typed per call, not planned), was addressed in
D47**: `agents/planner.py::plan_full_refresh` now builds the real multi-stage graph — selecting
which agents a goal needs and wiring correct dependency edges read directly off what each agent's
code actually queries/writes — from a high-level goal, verified live against the real database
with genuine cross-stage concurrency and correct ordering. This is still declarative graph
construction, not an AI planner deciding novel work from first principles — that distinction is
disclosed in the module itself, not implied away. Disagreement detection is not yet auto-scheduled
into the generated graph (a disclosed, real limitation, not silently dropped). Net: this remains a
well-built, well-tested parallel pipeline scheduler with real concurrency, retry, and
disagreement-detection engineering, now with real (if still fundamentally rule-based, not
learned/reasoning) task-graph construction on top — calling it "multiple autonomous agents that
reason independently" would still overstate it; calling it "orchestrated pipeline execution with
structured contracts, real concurrency, and real dependency-graph construction from a stated goal"
is accurate.

## 20. Application/UI audit — "what could I actually do with the application today?"

Today, a user can: open the SPA and see real projections/rankings (Rankings tab), see real EDGE
BUY/HOLD/SELL/WATCH classifications with reasons (EDGE tab), see real 2026 rookie projections and
click through to real historical comps (Rookies tab), see real evidence events (Evidence tab), load a
real Sleeper league's real context, see a real roster-need breakdown, and see a real draft-pick
recommendation for it (League tab), get a real FAAB bid recommendation for a specific waiver-wire
player (new Waiver tab), get a real single-player dynasty buy/hold/sell/watch evaluation (new Trade
tab), and check real per-source health status (Source Health tab). The UI/API architecture is clean:
thin projection over the API with zero logic duplication, and real error-state handling (confirmed: no
fake-data fallback anywhere).

**D44 closed the waiver/trade/roster-need gap** this section previously flagged: `WaiverView.tsx` and
`TradeView.tsx` (new files) wire the pre-existing, already-tested `postWaiver`/`postTrade` API client
functions into reachable tabs, and `LeagueView.tsx` gained a "Roster need" section calling the
pre-existing, already-tested `getRosterNeed`. All three were live-tested this session against the
real `dilworth` Sleeper league (season 2025) — see D44 in `docs/DECISIONS.md` for the exact
recommendations/reasons observed. **D49 later closed the one remaining gap this section flagged**
(a simulation-based team outlook) via `POST /simulate/team-season` + `SimulationView.tsx` — see
D49 in `docs/DECISIONS.md`.

## 21. Testing/engineering quality

Directly re-run this session, not assumed from history: **259/259 offline unit/leakage/contract
tests pass**; **42 network-marked tests deselected by default** (`pyproject.toml` `-m 'not
network'`), of which the league/Sleeper subset (6 tests) was run live this session and passed;
**ruff check and ruff format both clean**; **8/8 leakage tests pass**; **2/2 name-join contract
tests pass** (plus my own broader independent grep, also clean). `.github/workflows/ci.yml` runs
`make install && make lint && make test` on every push/PR to `main` — real, minimal CI, but note it
only runs the offline suite; the network-marked/live-integration tests (including the league/Sleeper
suite I ran manually this session) are **not** part of CI and would require credentials CI doesn't
have configured.

## 22. External dependencies/blockers (documentation only)

nflverse, DynastyProcess, cfbfastR-data, ffopportunity: reachable, primary path. Sleeper,
FantasyPros, CFBD: reachable and live-verified this session (superseding the still-stale note in
CLAUDE.md). KeepTradeCut, ESPN: still blocked by this environment's egress policy; DynastyProcess
substitutes KTC's dynasty-value role; nothing currently substitutes ESPN, and nothing in
PRODUCT_SPEC.md's core outputs strictly requires it.

## 23. Security/data governance

Current tracked tree is clean: `.env.example` contains only empty placeholders plus an explicit
warning comment referencing the prior incident; `.gitignore` correctly excludes `data/**`,
`models/**`, `predictions/**`, `reports/**`, `state/**`, `*.duckdb*`, and `.env*` (except
`.env.example`). **However, this run confirmed a live, unresolved exposure**: real API key values
from the previously-documented `docs/DECISIONS.md` D35 incident remain permanently retrievable via
`git log --all -p -- .env.example` — the leak was fixed forward (later commits are clean) but never
purged or rewritten from history, and this repository has a public-facing remote
(`github.com/gimann421/alpha-squad`). A broader pattern scan across all of git history found no
other secrets beyond the same two already-known values. **This exposure is not new to this audit run
and this audit does not fix it** (fixing it — history rewrite/key rotation confirmation — is exactly
the kind of destructive, irreversible action this audit was told not to perform); it is documented
here so it is tracked as an explicit, prioritized backlog item (see gap-analysis P0). The literal
leaked key substrings are intentionally not repeated in this file.

## 24. Technical debt / architectural problems, prioritized

Updated as P0-P2 backlog items closed this session (D41-D49); items resolved are marked as such
rather than deleted, so this section stays an accurate record of what was found and what changed.

1. ~~No model-artifact persistence anywhere~~ **RESOLVED (D43)** — `models/persistence.py`
   closes this for the two paths that actually serve live predictions (uncertainty → `/rankings`,
   rookie projection → `/rookies`); verified against the real database. Established-player models
   remain intentionally unpersisted since nothing serves their output live today (§6, D43).
2. **Leaked API keys still live in Git history** (§23) — still unresolved; D42 added a durable CI
   guardrail against a repeat but does not (and, per this audit's own rules, must not
   unilaterally) rewrite history. Still the single most important open item.
3. ~~Simulation is fully built and tested but invisible in the application~~ **RESOLVED (D49)** —
   `POST /simulate/team-season` + `SimulationView.tsx`, live-verified (real KC 2025 run, real
   named players, real QB/WR1 correlation). Also found and fixed why every simulation had been
   reporting "not enough history": `team_week_points` was empty because `build_team_week_points`
   had never been wired to a CLI command — added `alpha-squad features build-team-scores`. The
   last of the four "built but invisible" capabilities (waiver/trade/roster-need/simulation) is
   now closed.
4. ~~No committed EDGE historical-backtest report~~ **RESOLVED (D41)** — `alpha-squad edge
   backtest` + `reports/edge_backtest.md`, real per-position/bucket breakdown, run against
   current live-sourced data.
5. ~~Evidence-adjusted projections are computed but not consumed~~ **RESOLVED (D46)** — the
   architectural question was resolved by re-reading the source docs (PRODUCT_SPEC.md: "current
   information updates the prior") rather than assumed: evidence should reach served output, and
   now does, via `GET /rankings/weekly`, verified live.
6. ~~`LeagueContext.future_picks` is loaded but never read by the trade engine`~~ **RESOLVED
   (D45)** — real future-pick valuation (`pick_value`/`evaluate_trade_package`), verified against
   real dynasty-value data; `future_picks` itself remains intentionally unread since it is always
   empty in this deployment (no traded-picks data source) — pick assets are explicit caller input
   instead, per D45's reasoning.
7. **CI does not run the live/network-marked test suite** (§21) — still open; the Sleeper/league
   integration claims currently depend on someone manually running them, not an automated gate.
8. ~~CLAUDE.md's data-source-status note is stale~~ **RESOLVED (D50)** — rewritten to match
   `docs/DATA_SOURCES.md`'s current narrative, re-verified live against a fresh `sources status`
   run before editing.

## 25. Requirements vs. Reality

| Original Requirement | Intended Design | Actual Implementation | Gap | Severity |
|---|---|---|---|---|
| Reproducible historical predictions (ARCHITECTURE.md §13) | A prediction reconstructable from stored snapshots | Inputs are reconstructable; no frozen prediction artifact exists to reconstruct | No inference-time reproducibility, only training-input reproducibility | High |
| Multi-agent system with independent reasoning (AGENT_CONTRACTS.md) | Agents that decompose, critique, and resolve disagreement | Real scheduler/concurrency/state around agents that are thin pipeline-function wrappers | No real per-agent reasoning; the "intelligence" is the pipeline functions themselves, not the agents | Medium |
| Historical EDGE performance evaluated (PRODUCT_SPEC.md) | A documented backtest a reader can check | Backtest was run once; no artifact committed | Claim currently unverifiable from the repo alone | Medium |
| Evidence materially influences projections (PRODUCT_SPEC.md) | Evidence adjusts what's actually served | **RESOLVED (D46):** `GET /rankings/weekly` serves the evidence-adjusted value, ordered by it, with reasons — verified live | None remaining for the weekly path; season-level `/rankings` correctly stays unadjusted (evidence is in-season only) | Closed |
| Dynasty decisions account for future value (ACCEPTANCE_CRITERIA.md) | Future draft-pick value modeled | **RESOLVED (D45):** real `pick_value`/`evaluate_trade_package`, verified live | None remaining; `future_picks` itself stays unread by design (always empty, no data source) | Closed |
| Waiver/trade/roster-need reachable from the app (ACCEPTANCE_CRITERIA.md, Application section) | Every league decision type usable from the UI | **RESOLVED (D44):** draft, waiver, trade, and roster-need all wired into the SPA and live-verified against a real Sleeper league | None remaining for these three decision types | Closed |
| Team simulation reachable from the app (PRODUCT_SPEC.md's simulation-based outlook) | The Monte Carlo team-season engine usable from the UI | **RESOLVED (D49):** `POST /simulate/team-season` + `SimulationView.tsx`, live-verified with a real KC 2025 run (named players, real p10/p90 bands, real 0.335 QB/WR1 correlation). Also found and fixed the reason every team/season had reported "not enough history": `team_week_points` was empty because `build_team_week_points` had never been wired to a CLI command — added `alpha-squad features build-team-scores`, ran it for real | None remaining | Closed |
| Secrets never committed (ARCHITECTURE.md §15) | No API keys ever in tracked history | Current tree clean, but real keys from D35 remain in Git history permanently | Live exposure on a public remote | High |

## 26. Prioritized backlog (P0–P3)

See `docs/IMPLEMENTATION_GAP_ANALYSIS.md` for the full item-by-item breakdown with dependencies,
sequencing, and acceptance criteria — it has been refreshed alongside this section. Summary,
current as of D51:

- **P0:** ~~Resolve the leaked-key Git-history exposure~~ **the decision itself was already made
  (D35, at the time of the original leak: user explicitly declined a history rewrite)** — D42
  confirmed that and added a CI guardrail against a repeat instead. Not reopened; an autonomous
  session has no standing to perform a destructive, irreversible, shared-history rewrite on its
  own initiative regardless of whether more time has passed.
- **P1:** ~~Wire waiver/trade/roster-need into the UI~~ **done (D44)**. ~~Commit an EDGE
  historical-backtest report artifact~~ **done (D41)**. ~~Add model-artifact persistence~~ **done
  (D43)**, for the two paths that actually serve live predictions. ~~Wire the simulation engine
  into the API/UI~~ **done (D49)** — the last of the four "built but invisible" capabilities
  (waiver/trade/roster-need/simulation) identified at the start of this hardening pass, now all
  closed. No P1 items remain open.
- **P2:** ~~Feed evidence-adjusted projections into the actually-served projection~~ **done (D46)**
  — resolved by re-reading the source docs (evidence should reach served output, per
  PRODUCT_SPEC.md) rather than assumed. ~~Implement future-draft-pick valuation in the trade
  engine~~ **done (D45)**. Remaining: add the live/network suite to CI (gated to a scheduled job,
  given credential requirements).
- **P3:** ~~Refresh CLAUDE.md's stale data-source-status note~~ **done (D50)**. ~~Add an
  "in-season/ROS re-projection" loop if not already covered~~ **done (D46)** — the pipeline
  existed but had never been run against this deployment's data or served anywhere; both are now
  true. ~~Add expert-accuracy weighting to market-signal blending~~ **measured and resolved
  LIMITED (D51)** — real per-expert data is confirmed unavailable even from the live paid API, and
  the coarser proxy the data does permit showed no reliable signal against 1,925 real
  player-seasons; not adopted, per the same standard D39 established. No P3 items remain open.

Also closed this pass, not originally in the P0-P3 list: real task decomposition/dependency
discovery for the orchestrator (D47, was flagged as a genuine weak point in §19); a dead-code
sweep that found and fixed an unreachable `GET /players` endpoint plus a real label-forwarding
bug (D48); hardcoded, silently-stale season defaults across six views (D48); a real gap in
`team_week_points` reproducibility found while closing P1's simulation item (D49).

## 27. What can I do right now? (verified-working capabilities)

- Run `alpha-squad sources ingest` / `identity build` / `features build` / `train established-season`
  / `train rookie` / `evaluate baselines` and get real, walk-forward-validated results.
- Run `alpha-squad orchestrate run` and get the real orchestrator to build its own multi-stage task
  graph from a season range and run it with genuine concurrency (D47) — not just the original
  2-task `orchestrate demo`.
- Run `alpha-squad train uncertainty --persist` / `train rookie-project --persist`, then
  `alpha-squad models rescore-uncertainty` / `rescore-rookie-projection` and get a real prediction
  back from the saved model artifact with no retraining (D43).
- Run `alpha-squad edge backtest` and get a real, reviewable per-position/bucket EDGE performance
  report (D41) instead of trusting an unpreserved claim.
- Open the web app and see real preseason rankings, real weekly evidence-adjusted rankings with a
  "why did this change" reason per player (D46), real EDGE calls with reasons, real 2026 rookie
  projections with real historical comps, real evidence events, and real source-health status.
- Load a real registered Sleeper league (`dilworth` or `boys_of_fall`) and get: a real
  league-specific draft-pick recommendation with roster-fit reasoning and survival probability; a
  real waiver FAAB-bid recommendation; a real dynasty trade evaluation, now including real
  future-draft-pick valuation (D45); a real roster-need breakdown; and a real multi-asset trade
  comparison (players + picks on both sides, `league trade-package`) — all from UI buttons on the
  Waiver/Trade/League tabs, with player fields using real name search rather than raw id entry
  (D48), or via the CLI/API directly.
- Open the Simulation tab, pick a real team and season, and get a real correlated team-season
  Monte Carlo run back: real named players, real mean/p10/p90 season-point bands, and the real
  measured QB/WR1 stack correlation (D49) — via the UI or the CLI/API directly.
- Run the full offline test suite (303 passing), lint, and format checks and trust the result.
- **Cannot** currently: independently verify the D35 leaked keys have been rotated at their
  providers (outside what this repo can check).

## 28. Bottom line

**Maturity level: Functional V1, closer to Production Candidate than the original draft of this
audit found.** The core universal-intelligence pipeline (data → identity → features → established
ML → uncertainty → rookie ML → market/EDGE) is real, tested, and beats baselines with fresh,
honestly-computed evidence, now backed by a real inference-serving path (D43) instead of
retrain-per-request. The league-specific decision layer is real, live-verified against an actual
Sleeper league, and now covers all four decision types (draft/waiver/trade/roster-need, D44) plus
future-pick valuation (D45). Evidence genuinely reaches a served ranking (D46). The orchestrator
can build its own task graph (D47). The simulation engine is now reachable from the UI (D49) —
every capability originally flagged as "built but invisible" is now wired in. It is not yet fully
"Production Candidate" only because the D35 credential exposure remains open pending the user's
own provider-side action — a narrower, disclosed gap rather than an open question about whether
the core system works.

**Completion percentage: roughly 90%** of ACCEPTANCE_CRITERIA.md's items now land at
COMPLETE/VERIFIED or empirically-confirmed LIMITED (up from the original audit's 65–70% estimate)
— D41/D43/D44/D45/D46/D47/D48/D49/D50/D51 each moved multiple rows off PARTIAL/IMPLEMENTED-
UNVERIFIED/NOT-IMPLEMENTED. The only remaining gaps are the D35 decision (not a code fix) and
P2-3 (network suite in CI, needs a user credential decision).

**Strongest component:** the established-player ML pipeline and its walk-forward evaluation
methodology — genuinely leakage-safe, genuinely outperforms baselines, and, as of D43, actually
servable without retraining.

**Weakest component (as delivered to a user, not as code):** the live/network integration suite
still only runs manually, not as an automated CI gate (P2-3) — this project's live-source claims
depend on someone running `make test-network` by hand rather than a scheduled job catching a
break automatically. Genuinely low-risk (the offline suite covers correctness; this is about
catching upstream source drift), but it is the most concrete remaining gap now that every UI-
wiring item is closed.

**Biggest thing not to trust without re-checking:** the EDGE backtest's specific numeric findings
(now real and preserved, D41 — BUY beat market in all 4 scored seasons but SELL was genuinely
mixed) should be treated as a snapshot of one run against one market-data vintage, not a permanent
fact — re-run `alpha-squad edge backtest` after any material data refresh rather than citing the
numbers in `docs/DECISIONS.md` D41 indefinitely.

**Most important next thing to build:** nothing product-critical remains queued, and nothing left
in the backlog is autonomously actionable without a user decision. The one remaining item, P2-3
(network suite in CI), needs the user to decide whether to provision real API credentials as
GitHub Actions secrets — see `docs/IMPLEMENTATION_GAP_ANALYSIS.md`'s "Notes on sequencing."

**One recommended next action:** confirm with the user whether the D35-leaked API keys have
actually been rotated at their providers. The repo-side decision (no history rewrite, per D35/D42)
is settled and correctly so; the one remaining piece of that exposure this repo cannot verify on
its own is provider-side rotation, and it's the only item left in this backlog with real, present
risk rather than a functionality gap.

## 29–32. Output files and closing note

This file (`docs/CURRENT_STATE_AUDIT.md`) and `docs/IMPLEMENTATION_GAP_ANALYSIS.md` are the two
required deliverables of this audit. No implementation work was performed to produce them beyond
these two documentation files. This audit does not begin backlog work; see the accompanying summary
message for the stop point.

## Postscript (2026-08-25): productization phase (M15, D53)

Everything above is this audit's original snapshot and is kept as written. A later, separate
phase (M15) took the intelligence this audit found "substantial but partially inert" and built the
actual connect → understand → analyze → decide → explain path a real fantasy manager uses: runtime
Sleeper league onboarding, My Team roster intelligence, an Action Center (ranked ADD/DROP/TRADE),
batch waiver ranking, a Player Detail view separating universal from my-league value, and Draft/
Dashboard/multi-asset Trade-package views — all thin reads over the already-validated pipeline this
audit assessed, no new decision logic. Exercising the whole thing end to end with Playwright
against a real backend and a real Sleeper league (rather than trusting the code, the same standard
this audit itself modeled) found and fixed 6 further real bugs, three of them real concurrency
races that would have affected any real deployed user. Full account in `docs/DECISIONS.md` D53 and
`docs/PROJECT_STATE.md`'s M15 section. This audit's own "most important next thing to build"
conclusion above (nothing product-critical remained queued) was about the M1-M14 backlog
specifically, not a claim that the product was user-usable yet — M15 is what closes that gap.

## Postscript (2026-08-26): empirical validation phase (M16, D54)

M15 made the intelligence usable; M16 tested, adversarially, whether it is actually *good* —
this audit's own methodology extended from "does the code exist and run" to "does it beat
strong baselines on real historical outcomes." It found a genuine, previously-undetected product
bug this audit's code-level review could not have caught: `recommend_draft_pick`'s real draft
output loses to plain market consensus in every real historical season tested, because a
deliberately-bounded roster-fit multiplier cannot stop the recommender from stacking one
position (9 QBs; 11 WRs and 0 QBs, in two real trials) once that position's VORP runs hot for
several consecutive picks. This does not change this audit's "Strongest component" finding above
(the established-player ML pipeline's *point-value* accuracy is separately re-confirmed as
beating every baseline, D54) — the newly-found gap is specifically in the decision-logic layer
that turns good values into a pick sequence, not in the values themselves. Full account in
`docs/DECISIONS.md` D54, `docs/ALPHA_VS_BASELINES_EVALUATION.md`, and `docs/PROJECT_STATE.md`'s
M16 section. The fix is not yet implemented — tracked as the project's current top recommended
action, ahead of P2-3 in `docs/IMPLEMENTATION_GAP_ANALYSIS.md`.
