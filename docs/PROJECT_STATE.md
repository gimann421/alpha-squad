# Project State

Living summary of what is implemented, validated, and outstanding. Updated at the end of every
milestone. See `docs/TRACEABILITY.md` for the acceptance-criteria-level mapping.

## Status: M0 in progress

| Milestone | Status | Notes |
|---|---|---|
| M0 Bootstrap | IN PROGRESS | project skeleton, deps, docs |
| M1 Sources + snapshots | NOT STARTED | |
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

## Known limitations (see docs/DECISIONS.md for full reasoning)
- Sleeper, FantasyPros API, CollegeFootballData, KeepTradeCut, ESPN direct APIs are
  `BLOCKED_BY_POLICY` in this environment. Verified open-data substitutes are wired in instead
  (docs/DATA_SOURCES.md). Adapters for the blocked sources are implemented but inert.
- Per-expert accuracy weighting: LIMITED to source-level weighting (D4).
- Automated news/social evidence ingestion: LIMITED to structured official signals (D5).
