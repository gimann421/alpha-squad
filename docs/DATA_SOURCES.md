# Data Sources — Verified Status

Probed directly against the running environment on 2026-08-20 (see `docs/DECISIONS.md` D3).
**Re-verified 2026-08-22 (D31): the environment's network egress policy changed. Sleeper is now
fully AVAILABLE; FantasyPros and CFBD are now network-reachable and blocked only on missing
credentials (not policy) — see the D31 section below.**
**Re-verified 2026-08-23 (D36/D37): `CFBD_API_KEY` and `FANTASYPROS_API_KEY` were supplied and
are both now fully live. FantasyPros briefly appeared blocked (`403 Forbidden`) — that turned out
to be a wrong adapter base URL, not a credentials or policy problem; see D37.**
Re-run `alpha-squad sources status` for current status; this file is the narrative record of
point-in-time verifications, not a live document — always trust a fresh `sources status` run
over this file if they disagree.

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

### CollegeFootballData (`api.collegefootballdata.com`) — became AVAILABLE 2026-08-23, see D36
`CFBD_API_KEY` was supplied via this deployment's env-var config and confirmed live in a fresh
container: `teams` (1931 rows), `player_usage` (5197 rows), and `recruiting_players` (4120 rows,
after fixing the health check to pass a required `year` param — D36) all return real data with
the `Authorization: Bearer <key>` header already used by `sources/cfbd.py`. Fallback
(cfbfastR-data, D3) is no longer needed for college production but is left in place.

### FantasyPros API (`api.fantasypros.com`) — became AVAILABLE 2026-08-23, see D37
`FANTASYPROS_API_KEY` was supplied and confirmed live: `consensus_rankings` and `projections`
both return real data (`sources status`: 10 rows / 25 columns and 10 rows / 7 columns for the
default WR/ros health-check params). The `403 Forbidden` seen first (D36) was **not** a
credentials or policy problem — `sources/fantasypros.py`'s base URL was missing a `/public` path
segment (`api.fantasypros.com/v2/json/...` instead of the real `api.fantasypros.com/public/v2/json/...`,
confirmed against FantasyPros's own published API docs at `api.fantasypros.com/public/v2/docs`).
The wrong path still terminated at FantasyPros's real AWS API Gateway, which returned a genuine
`403`/`ForbiddenException` for a resource the key's usage plan doesn't cover — indistinguishable
from an invalid-key rejection without checking the docs. Fixed by correcting `_BASE`; no key
rotation was actually needed. Fallback (DynastyProcess `db_fpecr`/`values-players`, D3) is no
longer needed for consensus ECR but is left in place; per-expert weighting stays LIMITED
regardless (D4) — this key unlocks consensus ECR direct from source, not per-expert data.

Both adapters already refuse to call out without a key configured (`SourceCredentialsError`,
never a guessed/fabricated key) — set the env var and the real source activates with no further
code change needed now that both base URLs are correct.

**D38 addendum:** this key's free/public tier only serves `type=Draft` consensus rankings —
requesting `type=ROS` (or any other `SPORTRankingTypes` enum value) is silently accepted but
ignored; the response always echoes back `"type": "Draft"` regardless. Verified empirically,
not assumed from the docs. `market/consensus.py::build_live_fantasypros_snapshot` captures
this as a new `source='fantasypros_live'` series in `market_snapshot`, tagged `ecr_type='draft_overall'`
(not `'ros_overall'`, so the label never claims data this tier doesn't provide) — a separate,
provenance-tagged series accumulated forward from today, never blended into the DynastyProcess-sourced
historical rows `build_market_snapshot` builds. Also: CFBD's numeric athlete IDs
(`player_usage.id`, `recruiting_players.athleteId`, `draft/picks.collegeAthleteId`) were found
to be the exact same ID as DynastyProcess's `espn_id` (verified against 4/4 real players, no
fuzzy matching) — added to `identity/crosswalk.py`'s `DYNASTYPROCESS_ID_COLUMNS`, resolving
D20's college-production identity-bridge gap for rookie modeling (`features/college_production.py`).
See D38.

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
