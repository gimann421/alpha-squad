# Project State

Living summary of what is implemented, validated, and outstanding. Updated at the end of every
milestone. See `docs/TRACEABILITY.md` for the acceptance-criteria-level mapping.

## Status: M7 complete, M8 next

| Milestone | Status | Notes |
|---|---|---|
| M0 Bootstrap | DONE | project skeleton, deps, docs |
| M1 Sources + snapshots | DONE | 7 adapters (4 available, 3 blocked/no-creds), all verified live; 25 offline + 6 network tests passing; one real bug found and fixed in review (see below) |
| M2 Canonical identity | DONE | player_id spine (25,046 players) + 25 crosswalk ID types + college bridge, all verified against live data; 43 offline + 8 network tests passing; three real bugs found and fixed in review (see below) |
| M3 As-of features + leakage | DONE | games/player_week_stats/player_week_features (199,632 rows over 2015-2025, built in ~7s from cache); leakage-safe by construction via SQL window frames; 51 offline (incl. 12 leakage tests with independent Python recomputation) + 9 network tests passing |
| M4 Baselines + evaluation | DONE | 3 baselines (previous-year, weighted-2yr, ECR-implied) walk-forward evaluated 2018-2025 against 21,421 real player-seasons and 210,730 real market snapshots; shared evaluation harness (MAE/RMSE/R²/Spearman/top-N hit rate/tier accuracy) reused by every later milestone; 65 offline + 10 network tests passing. **One number in this milestone's report was wrong and got corrected in M5 — see D19.** |
| M5 Established-player ML | DONE | Position-specific Ridge/CatBoost/XGBoost + opportunity-only + team-environment-only + ensemble, both weekly (in-season) and season-level (preseason, apples-to-apples vs M4); team_week_stats/features extend the M3 panel; model_registry tracks version/validation; 70 offline + 12 network tests passing. One real evaluation-harness bug found and fixed (D19), affecting M4's reports too. |
| M6 Uncertainty + calibration | DONE | Split-conformal p10/p25/median/p75/p90 + Monte Carlo top-12/24 probabilities on the M5 season-level CatBoost model; walk-forward 3-way split (train/calibrate/target) so calibration is genuinely out-of-sample; real measured coverage_10_90 mostly 0.72-0.90 (target 0.80) across 2019-2025/QB-RB-WR-TE — legitimately well-calibrated, not just plausible-looking; 82 offline + 13 network tests passing |
| M7 Rookie/prospect intelligence | DONE | Draft capital + combine + prior-season landing-spot features (college production LIMITED — no verified ID bridge to cfbfastR exists, D20); CatBoost regression (rookie-year PPR) + classifier (top-24 breakout, Brier-scored) walk-forward by draft class; nearest-neighbor historical comps; 1,077 real rookie-seasons, 88 offline + 15 network tests passing; two real bugs found and fixed (combine height stored as "6-0" string, comps dtype crash) |
| M2 Canonical identity | NOT STARTED | |
| M3 As-of features + leakage | NOT STARTED | |
| M4 Baselines + evaluation | NOT STARTED | |
| M5 Established-player ML | NOT STARTED | |
| M6 Uncertainty | NOT STARTED | |
| M7 Rookie modeling | NOT STARTED | |
| M8 Market + EDGE | NOT STARTED | |
| M9 Evidence engine | NOT STARTED | |
| M10 League decision engine | NOT STARTED | |
| M11 Agents/orchestrator | NOT STARTED | |
| M12 API + frontend | NOT STARTED | |
| M13 Hardening | NOT STARTED | |

## M1 summary
- Adapters: `nflverse` (15 datasets), `dynastyprocess` (4), `cfbfastr` (1), `ffopportunity` (1)
  — all AVAILABLE, verified against the live sources (both mocked-contract tests and
  `network`-marked live tests). `sleeper` (6 endpoints) verified BLOCKED_BY_POLICY;
  `fantasypros` (2) and `cfbd` (3) verified NO_CREDENTIALS, and both provably never attempt a
  network call without a configured key (see `test_fantasypros_without_key_never_makes_network_call`
  / `test_cfbd_without_key_never_makes_network_call`).
- `snapshot_registry` + `source_health_log` tables in DuckDB; every fetch writes an immutable
  file under `data/raw/<source>/<dataset>/captured_at=<date>/...` and is content-hashed.
- `alpha-squad sources status` and `alpha-squad sources ingest --season-start Y --season-end Y`
  both real, run against live sources. A multi-season smoke ingest (2023-2026) produced 46 real
  snapshots and correctly reported 8 NOT_FOUND for genuinely unpublished 2026 weekly/game-level
  datasets — nothing fabricated.
- Two real bugs found and fixed during self-review (not just written and assumed correct):
  1. `sources status` was writing real files to disk and reporting AVAILABLE without ever
     calling `record_snapshot`, so the registry silently stayed empty while the CLI reported
     success. Fixed by making status and ingest share the same fetch+record path; regression
     tests in `tests/unit/test_storage_snapshots.py`.
  2. `Settings` fields use `validation_alias` (so env vars match `.env.example`'s names) but
     without `populate_by_name=True`, pydantic silently dropped `Settings(data_dir=...)`-style
     kwargs and fell back to defaults, with `extra="ignore"` hiding the resulting
     ValidationError — meaning test fixtures believed they were isolated to `tmp_path` but
     were actually writing into the real repo `data/` directory. Fixed; regression tests in
     `tests/unit/test_settings.py`.

## M2 summary
- `players` (25,046 rows): spine anchored on nflverse `players.gsis_id` — verified 100%
  populated, unique. `player_id = 'asq_' || substr(md5(gsis_id), 1, 16)`, deterministic (not
  a persisted counter), so rebuilds are reproducible.
- `player_id_map` (25 id_types, ~180k rows total): normalized ID-to-ID crosswalk — 8 native
  nflverse IDs (gsis/pfr/espn/otc/esb/nfl/smart/pff) + 15 DynastyProcess IDs (mfl/sleeper/
  yahoo/ktc/etc.) + cfb_player_id (draft_picks) + cfb_id (combine). `(id_type, id_value)` is
  a hard PRIMARY KEY; `insert_id_mappings()` detects and quarantines collisions *before*
  writing rather than relying on the constraint to fail the whole build.
- `player_college_bridge`: 7,990 `cfb_player_id` + 6,131 `cfb_id` mappings, feeding rookie
  modeling (M7) directly from real draft_picks/combine data.
- `identity_exceptions`: 1,639 rows on first build (1,152 unmapped historical draft picks,
  389 unmapped combine prospects who never made a roster, 70 orphan DynastyProcess gsis_ids,
  28 genuinely self-inconsistent DynastyProcess rows) — quarantined, not dropped or guessed.
  Idempotent by design: re-running the build never reverts a human-resolved exception back
  to PENDING (regression-tested).
- Full build against live data: ~13 seconds, zero integrity violations (no duplicate keys,
  no orphaned foreign keys, no null gsis_id) — verified by both a live network test and
  direct inspection.
- Three real bugs found and fixed during self-review before considering this done:
  1. **Hash algorithm mismatch**: `mint_player_id()` (Python, for code needing an ID without
     a DB round-trip) used sha256 while the embedded SQL used md5 — would have minted two
     different IDs for the same gsis_id depending on code path. Fixed by extracting a single
     `PLAYER_ID_SQL_EXPR` constant both paths use; regression-tested for parity.
  2. **Severe performance bug**: `insert_id_mappings` and the college-bridge upsert looped
     over matched rows in Python, calling `con.execute()` once per row — profiled at 88
     seconds for 25,000 rows (~3.5ms/call overhead), which made a full identity build hang
     for minutes across ~25 id_types. Rewritten as set-based `INSERT...SELECT...RETURNING`
     (one round trip per id_type); full build now takes ~13s. `executemany()` was profiled
     too and found equally slow — the fix is genuinely set-based SQL, not a different batch
     API.
  3. **Wrong join target**: the draft_picks/combine college-bridge builders assumed a
     `players.pfr_id` column that doesn't exist — pfr_id (like every other native ID) lives
     in `player_id_map`, not denormalized onto `players`. Fixed to join through
     `player_id_map WHERE id_type='pfr_id'`.
- Real DynastyProcess data-quality issues discovered and handled (docs/DECISIONS.md D12/D13):
  the CSV export uses the literal string `"NA"` for missing values in every column including
  IDs (handled via `nullstr=['NA']`), and the export itself contains internally-inconsistent
  duplicate gsis_id rows (e.g. one gsis_id mapped to two different player names) — quarantined
  rather than trusting whichever row loaded first.

## M3 summary
- `games` (3,028 rows, 2015-2025): derived from `pbp`'s `game_id`/`game_date` since nflverse
  publishes no separate schedules dataset (verified 404) — the anchor for every as-of check.
- `player_week_stats` (199,632 rows): normalized `stats_player_week` + `snap_counts`,
  identity-joined once (gsis_id direct to spine; pfr_id through `player_id_map` for snaps,
  same pattern as the M2 college bridge).
- `player_week_features` (199,632 rows): the engineered lag/rolling panel — leakage-safe *by
  construction* via SQL window frames (`ROWS BETWEEN N PRECEDING AND 1 PRECEDING`), not by
  trusting a date filter. `target_fantasy_points_ppr` is the real unlagged outcome, kept only
  as the training target.
- `features_as_of(con, date)` is a second, independent row-level safety layer (`game_date <
  as_of`, strict) for reconstructing "what was known as of date D" — verified both offline
  and against real data that a game on the as-of date itself is correctly not yet visible.
- Leakage tests (tests/leakage/): poison/sentinel injection, target isolation via independent
  Python recomputation (not reusing the SQL under test), season-reset verification, and
  rebuild-invariance (appending future weeks and rebuilding must not change historical rows'
  stored features) — all passing, both offline (synthetic fixtures) and against real data.
- Full build against 11 real seasons (2015-2025) of cached data: ~7 seconds.

## M4 summary
- `player_season_stats` (21,421 rows): season aggregate of M3's `player_week_stats`.
- `market_snapshot` (210,730 rows): normalized DynastyProcess `fp_ecr_history` ('ro'
  redraft-overall series), identity-joined via `fantasypros_id` (verified 93.8% coverage —
  D16). Extended in M8 with the 2QB-aware series the target league (D7) actually needs.
- Three baselines, all walk-forward (season S predictions read only data from before S):
  `baseline_previous_year`, `baseline_weighted_2yr` (0.65/0.35), `baseline_ecr_implied`
  (isotonic rank-to-points calibration curve, fit per position on an expanding window of
  prior seasons only — D17). "ADP-implied" is LIMITED to this same ECR-based substitute; no
  independent ADP series is reachable (D16).
- Shared evaluation harness (`models/evaluate.py`): MAE, RMSE, R², Spearman, top-12/24 hit
  rate, tier accuracy — computed overall and per position, persisted to `evaluation_results`,
  published to `reports/baseline_evaluation.md`. Every later model (M5, M7, M8) reports
  through the same harness so comparisons are apples-to-apples, per ACCEPTANCE_CRITERIA.md.
- **Correction (superseded by the M5 fix below):** an earlier version of this section claimed
  the ECR-implied baseline's MAE was "substantially worse" than the simple historical
  baselines' based on comparing ecr_implied's correctly-scoped MAE (~45-49) against the other
  two baselines' *unscoped* "ALL positions" MAE (~14-15). That comparison was invalid — see
  docs/DECISIONS.md D19. With the fix, all three baselines land in the same ~45-53 MAE range
  for "ALL" (QB/RB/WR/TE only), a much more sensible result.

## M5 summary
- `team_week_stats`/`team_week_features` (6,056 rows): team-environment signal (plays, pass
  rate, EPA) from `stats_team_week`, leakage-safe by construction (same window-frame pattern
  as M3), attached onto `player_week_features` by (team, season, week).
- **Weekly/in-season models** (`models/established/train.py`): Ridge, CatBoost, XGBoost,
  plus standalone opportunity-only and team-environment-only models (isolating each signal's
  own predictive power — team-environment alone is markedly the weakest, MAE 30-56 vs 10-19
  for the full models, exactly as expected: team context alone barely predicts individual
  output), and an ensemble that's only marked `validated=True` in `model_registry` when it
  beats every component model's MAE out of sample that season (ARCHITECTURE.md §5/§12).
  Trains on seasons < S, predicts every week of season S using that week's already-lagged
  features, aggregates to a season total for comparison. Real result: Spearman 0.94-0.98,
  MAE 10-19 for the full models — strong, because this task has access to season S's own
  in-progress weeks (a genuinely different, easier task than preseason projection).
- **Season-level/preseason models** (`models/established/season_level.py`): Ridge, CatBoost,
  XGBoost trained on season S-1 aggregate + preseason ECR rank only — the actual
  apples-to-apples comparison against M4's baselines, since both use only pre-S information.
  Real, modest, genuine result: e.g. WR 2024, `ml_season_catboost` MAE 44.27 vs the best M4
  baseline (`ecr_implied`) at 45.05 — CatBoost edges out every baseline slightly, without
  overclaiming a dramatic win. Documented per-position, not hidden either way.
- Two model families, not one, precisely because comparing the weekly model against M4
  baselines would have overstated ML's advantage (different information sets) — see D18.
- **Real bug found and fixed during this milestone's review**: `models/evaluate.py`'s "ALL
  positions" rollup pooled *every* position in `player_season_stats` (LB, CB, K, P, etc. —
  ~900 of 1,512 rows for 2024), most of which correctly score ~0 PPR points. Their
  near-perfectly-predictable near-zero outcomes diluted the pooled MAE to ~14.7, while every
  individual skill position's real MAE was 33-65 — a materially misleading number that had
  been silently wrong since M4. Fixed with `SKILL_POSITIONS = ("QB","RB","WR","TE")` scoping
  the "ALL" rollup; per-position numbers were never affected (D19). All M4 and M5 evaluation
  reports were regenerated after the fix; regression-tested.

## M6 summary
- `uncertainty_predictions`: p10/p25/median/p75/p90 + top12_prob/top24_prob + a documented
  confidence heuristic, one row per (player, season, model_version) — field names mirror
  AGENT_CONTRACTS.md's Prediction contract directly.
- Split-conformal method (`models/uncertainty/conformal.py`): signed calibration-residual
  quantiles (not a symmetric margin), so intervals can be asymmetric — verified this matters
  with a synthetic right-skewed-residual test (p90 offset larger in magnitude than p10).
  Three-way, strictly time-ordered split per target season S: proper-train (< S-1) ->
  calibration (S-1 only, held out from training) -> target (S). Top-12/24 probabilities via
  Monte Carlo: resample from the empirical calibration-residual distribution 2,000x per
  player, rank within the simulated draw, measure how often each player lands in the top
  12/24 among their position peers.
- `calibration_diagnostics`: out-of-sample empirical coverage, published to
  `reports/calibration_report.md`. Real result on 2019-2025 QB/RB/WR/TE: coverage_10_90
  mostly 0.72-0.90 against a target of 0.80 (one outlier at 0.69, WR 2024) —
  genuinely close to nominal, not just directionally plausible. This is the "measure
  calibration" / "do not present false precision" requirement actually verified against real
  data, not asserted.
- 3,120 real predictions written on the full 2019-2025 run.

## M7 summary
- `combine_results` (7,031 rows): athletic testing bridged via `pfr_id` through
  `player_id_map`, same pattern as M3's snap counts.
- `rookie_features` (1,077 real rookie-seasons, 2016-2025 shown at ~90-103/class): draft
  capital (direct from `players`), combine testing, and landing spot (drafting team's
  *prior*-season pass rate/plays — never the rookie's own season, to avoid a look-ahead).
  breakout_top24 derived from actual within-position season rank, not a hardcoded points
  threshold.
- College production is LIMITED: cfbfastR-data's college identifiers are numeric ESPN-style
  IDs with no verified bridge to the nflverse-derived identity graph, and its "player_stats"
  dataset is raw play-by-play, not aggregated season totals — building both a fuzzy-match
  bridge and touchdown-attribution aggregation was judged a materially larger undertaking
  than this milestone's budget justified, especially since draft capital already
  substantially proxies for it (D20). Not fabricated via a shaky join; documented as a real
  gap with a defensible fallback.
- CatBoostRegressor (rookie-year PPR points) + CatBoostClassifier (top-24 breakout,
  Brier-scored) walk-forward strictly by draft class (train on classes < C, predict C).
  Real results: regression Spearman mostly 0.4-0.8 (rookie prediction is inherently noisier
  than established-player prediction — no prior NFL data exists), breakout Brier scores
  mostly 0.02-0.12 against base rates of 2-27%.
- Historical comps (nearest-neighbor on standardized draft capital + combine, never drawing
  from the target's own or a later class): spot-checked against real 2023 RB rookies —
  Jahmyr Gibbs' and Bijan Robinson's top comps were plausible past first-round backs
  (Ezekiel Elliott, Clyde Edwards-Helaire).
- Two real bugs found and fixed during this milestone's review:
  1. Combine's `ht` column is a feet-inches string (`"6-0"`), not a number — a direct
     `CAST(... AS DOUBLE)` failed outright. Fixed by parsing `split_part` into inches.
  2. The comps nearest-neighbor crashed with a dtype error (`'float' object has no
     attribute 'sqrt'`) because the query-target row's integer columns came back as pandas
     nullable Int64 (bypassing `load_rookie_class_data`'s imputation), producing an
     object-dtype array `np.linalg.norm` couldn't handle. Fixed with an explicit
     `.astype(float)` after concatenation.

## Known limitations (see docs/DECISIONS.md for full reasoning)
- Sleeper, FantasyPros API, CollegeFootballData, KeepTradeCut, ESPN direct APIs are
  `BLOCKED_BY_POLICY` in this environment. Verified open-data substitutes are wired in instead
  (docs/DATA_SOURCES.md). Adapters for the blocked sources are implemented but inert.
- Per-expert accuracy weighting: LIMITED to source-level weighting (D4).
- Automated news/social evidence ingestion: LIMITED to structured official signals (D5).
- ADP-implied baseline: LIMITED to the ECR-implied substitute; no independent ADP series is
  reachable (D16).
- Rookie college production: LIMITED — no verified ID bridge from cfbfastR-data's numeric
  ESPN-style player IDs to the rest of the identity graph, and its "player_stats" dataset is
  raw play-by-play, not aggregated season totals (D20). Rookie model v1 uses draft capital +
  combine + landing spot, all cleanly identity-linked.
