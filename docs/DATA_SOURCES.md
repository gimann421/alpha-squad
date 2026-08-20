# Data Sources — Verified Status

Probed directly against the running environment on 2026-08-20 (see `docs/DECISIONS.md` D3).
Re-run `alpha-squad sources status` for current status; this file is the narrative record of the
initial verification, not a live document.

## AVAILABLE

### nflverse (`github.com/nflverse/nflverse-data` release assets)
No auth required. Access via `https://github.com/nflverse/nflverse-data/releases/download/<tag>/<file>`,
following redirects (`curl -L`; resolves through `release-assets.githubusercontent.com`).

| Dataset | Release tag | Coverage verified |
|---|---|---|
| Players master | `players` | current |
| Weekly player stats | `stats_player` (NOT the older `player_stats` tag) | 1999–2025 |
| Weekly team stats | `stats_team` | 2025 |
| Rosters (season) | `rosters` | 2026 |
| Weekly rosters | `weekly_rosters` | 1999-2026 |
| Depth charts | `depth_charts` | 2025, 2026 (current) |
| Injuries | `injuries` | through 2025 |
| Snap counts | `snap_counts` | 2012+ |
| Draft picks | `draft_picks` | full history; includes `cfb_player_id` (college↔NFL bridge) |
| Combine | `combine` | full history; `forty/bench/vertical/broad_jump/cone/shuttle`, `cfb_id` |
| Play-by-play | `pbp` | 1999–2025, ~20MB/season |
| FTN charting | `ftn_charting` | 2022+ |
| Next Gen Stats | `nextgen_stats` | passing/rushing/receiving aggregates |
| ESPN QBR | `espn_data` | season-level |
| Contracts | `contracts` | historical |

### DynastyProcess (`raw.githubusercontent.com/dynastyprocess/data/master/files/`)
No auth required.

| File | Contents | Verified |
|---|---|---|
| `db_playerids.csv` | 12,473-row ID crosswalk: mfl/sportradar/**fantasypros**/gsis/pff/**sleeper**/nfl/espn/yahoo/fleaflicker/cbs/pfr/cfbref/rotowire/**ktc**/stats/swish ids + name/position/team/birthdate/draft info | ✓ |
| `db_fpecr.parquet` | Historical FantasyPros ECR, 38.7MB, `scrape_date`+`ecr_type`+`best`/`worst`/rank dispersion — this is the market time series used for as-of joins and EDGE backtesting | ✓ |
| `values-players.csv` | Current dynasty values: `ecr_1qb`, **`ecr_2qb`**, `value_1qb`, `value_2qb`, fresh as of 2026-08-14 | ✓ |
| `values-picks.csv` | Dynasty rookie pick values | ✓ |

Note: repo `raw/` paths (`github.com/<org>/<repo>/raw/...`) return policy 403; use
`raw.githubusercontent.com/<org>/<repo>/<branch>/...` instead.

### cfbfastR-data (`raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/`)
College production for rookie modeling. `player_stats/parquet/player_stats_{season}.parquet`
verified for 2024, 2025 (5.2MB). Note: `github.com/.../raw/...` and `api.github.com` for this repo
are blocked; must use `raw.githubusercontent.com`.

### ffopportunity (`github.com/ffverse/ffopportunity` release assets)
`ep_weekly_{season}.parquet` — expected fantasy points per play, used in the opportunity model.
Verified 2024, 2025.

## BLOCKED (environment egress policy — `403` at CONNECT, confirmed via proxy status as
`connect_rejected`, not a credentials issue)

| Source | Host | Spec role | Fallback in use |
|---|---|---|---|
| Sleeper | `api.sleeper.app` | league/roster/draft state, trending adds | Local league-context YAML (D6); ID crosswalk via DynastyProcess |
| FantasyPros API | `api.fantasypros.com` | ECR/ADP/projections, per-expert rankings | DynastyProcess `db_fpecr`/`values-players` (D3); per-expert weighting LIMITED (D4) |
| CollegeFootballData | `api.collegefootballdata.com` | college production/usage | cfbfastR-data (D3) |
| KeepTradeCut | `keeptradecut.com` | dynasty market value | DynastyProcess `values-players`/`values-picks` (D3) |
| ESPN public API | `site.api.espn.com` | not a required core source | unused, marked BLOCKED |

Adapters for all five are implemented in `src/alpha_squad/sources/` to the same interface as the
working adapters. Calling them raises `SourceBlockedError` and records `BLOCKED_BY_POLICY` in the
snapshot registry — they never silently return empty or fabricated data. If egress policy changes,
no code change is required beyond re-running `alpha-squad sources status`.

## Also blocked
`api.github.com` itself returns policy 403 for most calls in this environment (only some paths
work). Do not depend on the GitHub REST API for dataset discovery; use known
`raw.githubusercontent.com` / release-asset URLs directly.
