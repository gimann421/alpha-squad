# Project State

Living summary of what is implemented, validated, and outstanding. Updated at the end of every
milestone. See `docs/TRACEABILITY.md` for the acceptance-criteria-level mapping.

## Status: M2 complete, M3 next

| Milestone | Status | Notes |
|---|---|---|
| M0 Bootstrap | DONE | project skeleton, deps, docs |
| M1 Sources + snapshots | DONE | 7 adapters (4 available, 3 blocked/no-creds), all verified live; 25 offline + 6 network tests passing; one real bug found and fixed in review (see below) |
| M2 Canonical identity | DONE | player_id spine (25,046 players) + 25 crosswalk ID types + college bridge, all verified against live data; 43 offline + 8 network tests passing; three real bugs found and fixed in review (see below) |
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

## Known limitations (see docs/DECISIONS.md for full reasoning)
- Sleeper, FantasyPros API, CollegeFootballData, KeepTradeCut, ESPN direct APIs are
  `BLOCKED_BY_POLICY` in this environment. Verified open-data substitutes are wired in instead
  (docs/DATA_SOURCES.md). Adapters for the blocked sources are implemented but inert.
- Per-expert accuracy weighting: LIMITED to source-level weighting (D4).
- Automated news/social evidence ingestion: LIMITED to structured official signals (D5).
