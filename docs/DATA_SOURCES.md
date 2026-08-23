# Data Sources — Verified Status

Probed directly against the running environment on 2026-08-20 (see `docs/DECISIONS.md` D3).
**Re-verified 2026-08-22 (D31): the environment's network egress policy changed. Sleeper is now
fully AVAILABLE; FantasyPros and CFBD are now network-reachable and blocked only on missing
credentials (not policy) — see the D31 section below.** Re-run `alpha-squad sources status` for
current status; this file is the narrative record of point-in-time verifications, not a live
document — always trust a fresh `sources status` run over this file if they disagree.

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

### Sleeper (`api.sleeper.app`) — became AVAILABLE 2026-08-22, see D31
No auth required. `state`, `players`, `trending_adds`, `trending_drops` all verified with real
data (2026-08-22): real NFL season state, the full ~12k-player pool, 25 real trending-add/drop
entries each. `league`/`league_rosters`/`league_drafts` are real, working endpoints too — the
health check's placeholder `league_id=0` correctly 404s since no such league exists; give a real
league ID to pull real league state. As designed, this activated with no code change once the
policy opened (`sources/sleeper.py`).

## Network-reachable but credential-gated (not a policy block — see D31)

| Source | Host | What's needed | Current fallback |
|---|---|---|---|
| FantasyPros API | `api.fantasypros.com` | paid `FANTASYPROS_API_KEY` (network layer confirmed open 2026-08-22: real `{"message":"Forbidden"}` app-level response with no key) | DynastyProcess `db_fpecr`/`values-players` (D3); per-expert weighting stays LIMITED regardless (D4) — a key unlocks consensus ECR direct from source, not per-expert data |
| CollegeFootballData | `api.collegefootballdata.com` | free `CFBD_API_KEY` from collegefootballdata.com (network layer confirmed open 2026-08-22: real, detailed "missing Bearer key" response) | cfbfastR-data (D3) |

Both adapters already refuse to call out without a key configured (`SourceCredentialsError`,
never a guessed/fabricated key) — set the env var and the real source activates with no code
change.

## Still policy-blocked or otherwise unavailable

| Source | Host | Spec role | Fallback in use |
|---|---|---|---|
| KeepTradeCut | `keeptradecut.com` | dynasty market value | No formal adapter exists (site, not an API) — DynastyProcess `values-players`/`values-picks` (D3). Bare-domain reachability re-checked 2026-08-22 (HTTP 200), but nothing in this codebase calls it. |
| ESPN public API | `site.api.espn.com` | not a required core source | unused; bare-domain check 2026-08-22 returned a real app-level 403 (not a network block), still unused either way |

Adapters are implemented in `src/alpha_squad/sources/` to the same interface as the working
adapters, and activate with no code change as their blockers clear — `SourceBlockedError`/
`SourceCredentialsError` is raised and recorded rather than ever silently returning empty or
fabricated data. **This is not a fixed list: re-run `alpha-squad sources status` periodically —
this environment's network policy has already changed once (D3 → D31) and may again.**

## Also not usable for this project, for an unrelated reason
`api.github.com` is reachable at the network layer (re-checked 2026-08-22), but real repo calls
(e.g. `/repos/nflverse/nflverse-data`) 403 with a Claude Code Remote session message about
repository scope, not a network-policy or GitHub-API error — this session's GitHub access is
scoped to specific attached repos, and nflverse-data was never one of them (nor does it need to
be: the project only ever reads `raw.githubusercontent.com` release-asset URLs directly, which
has worked throughout). Do not depend on the GitHub REST API for dataset discovery either way.
