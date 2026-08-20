# Project State

Living summary of what is implemented, validated, and outstanding. Updated at the end of every
milestone. See `docs/TRACEABILITY.md` for the acceptance-criteria-level mapping.

## Status: M1 complete, M2 next

| Milestone | Status | Notes |
|---|---|---|
| M0 Bootstrap | DONE | project skeleton, deps, docs |
| M1 Sources + snapshots | DONE | 7 adapters (4 available, 3 blocked/no-creds), all verified live; 25 offline + 6 network tests passing; one real bug found and fixed in review (see below) |
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

## Known limitations (see docs/DECISIONS.md for full reasoning)
- Sleeper, FantasyPros API, CollegeFootballData, KeepTradeCut, ESPN direct APIs are
  `BLOCKED_BY_POLICY` in this environment. Verified open-data substitutes are wired in instead
  (docs/DATA_SOURCES.md). Adapters for the blocked sources are implemented but inert.
- Per-expert accuracy weighting: LIMITED to source-level weighting (D4).
- Automated news/social evidence ingestion: LIMITED to structured official signals (D5).
