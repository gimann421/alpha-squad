# Decisions Log

Durable record of assumptions and resolutions made while executing
`CLAUDE_CODE_LEAD_PROMPT.md`. Append-only; do not delete superseded entries — mark them
superseded instead.

## D1 — Original v1 documents absent
`CLAUDE_CODE_LEAD_PROMPT.md` §1 references `fantasy_football_ml_ai_model_spec_v1.md` and three
sibling documents. They are not present in the repository. The consolidated package
(`PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `ACCEPTANCE_CRITERIA.md`,
`AGENT_CONTRACTS.md`) is treated as authoritative, per `README.md`: "The consolidated package
resolves implementation-workflow conflicts... while preserving product requirements."

## D2 — Python 3.12
`ARCHITECTURE.md` §14 requires Python 3.12+. The environment default is 3.11.15, but
`/usr/bin/python3.12` (3.12.3) is present. Project pins `>=3.12` and uses `uv` to select it.

## D3 — Verified data-source reachability (2026-08-20)
Probed directly rather than assumed, per lead prompt §4. Full table in `docs/DATA_SOURCES.md`.
Summary: nflverse, DynastyProcess (FantasyPros ECR history/current + dynasty values + ID
crosswalk), cfbfastR-data (college production), ffopportunity (expected fantasy points) are all
reachable over HTTPS via `raw.githubusercontent.com` / GitHub release assets. Direct calls to
`api.sleeper.app`, `api.collegefootballdata.com`, `api.fantasypros.com`, `keeptradecut.com`, and
`site.api.espn.com` return `403` at the environment's egress proxy (policy denial, confirmed via
`/root/.ccr/__agentproxy/status` — `connect_rejected`, not an auth failure).

**Resolution:** implement adapters for the blocked sources exactly as specified (same request
shape, same schema mapping) so they activate unchanged if the policy or credentials change. Until
then they raise and register `BLOCKED_BY_POLICY` in the source health registry — never return
fabricated or empty-but-silent data. Use the verified open substitutes as the operating data path:

| Spec source | Blocked transport | Verified substitute in use |
|---|---|---|
| FantasyPros ECR/ADP | `api.fantasypros.com` | DynastyProcess `db_fpecr.parquet` (historical, `scrape_date`) + `values-players.csv` (current, includes `ecr_2qb`) |
| Sleeper | `api.sleeper.app` | DynastyProcess `db_playerids.csv` for `sleeper_id` crosswalk; league state itself loaded from local YAML (see D6) |
| CollegeFootballData | `api.collegefootballdata.com` | cfbfastR-data `player_stats_{season}.parquet` |
| KeepTradeCut | `keeptradecut.com` | DynastyProcess `values-players.csv` / `values-picks.csv` (dynasty value, distinct signal from ECR) |
| ESPN | `site.api.espn.com` | Not substituted; not a core required source. Marked BLOCKED, unused by v1. |

This is not a product simplification: the same underlying signals (consensus ECR, dynasty market
value, college production, ID crosswalks) are present, sourced from the data providers' own open
distributions rather than blocked JSON APIs.

## D4 — Per-expert accuracy weighting: LIMITED
`PRODUCT_SPEC.md` calls for "expert rankings weighted by demonstrated accuracy." Only FantasyPros
*consensus* ECR (best/worst/average across anonymized experts) is reachable; individual expert
identity requires the blocked FantasyPros API. Weighting is implemented at the *source* level
(consensus ECR vs. dynasty market value vs. model) instead of per-expert. Marked LIMITED in
`docs/TRACEABILITY.md` with this reason; the per-expert path is not deleted, just unreachable.

## D5 — Free-text news evidence: LIMITED
No news/social API is reachable in this environment. `news_evidence` evidence events are derived
from structured official signals already ingested: depth-chart rank deltas, injury-report status
transitions, roster transactions, and week-over-week snap/route/target share shifts — all of which
satisfy the "strong evidence" definition in `PRODUCT_SPEC.md` §Evidence. A manual/CLI evidence
entry path is also implemented, conforming to the evidence contract, for evidence a human supplies
(e.g. a beat reporter's report copied in by a user). Fully automated ingestion of "medium"/"weak"
tier evidence (beat reports, social media, camp buzz) is BLOCKED for lack of a reachable source.

## D6 — League context source
`Sleeper` (the natural live source for roster/draft/waiver state per `PRODUCT_SPEC.md`) is
blocked. League context is loaded from a local YAML file matching the
`AGENT_CONTRACTS.md` league-context contract exactly. The Sleeper adapter is implemented and will
hydrate the same contract automatically once reachable — no schema change required.

## D7 — Target league type
`ARCHITECTURE.md`/`IMPLEMENTATION_PLAN.md`/`PRODUCT_SPEC.md` all state the target league is 10
teams, 2 QB, 2 RB, 2 WR, 1 TE, 2 FLEX. `AGENT_CONTRACTS.md`'s worked example additionally sets
`"format": "dynasty"`. Neither bench size nor FAAB budget is specified anywhere.
**Decision:** treat the target league as dynasty PPR (per the contract example), and produce both
redraft-season and dynasty outputs (both are required product outputs per
`ACCEPTANCE_CRITERIA.md`; nothing says the target league is the only league instance). Default
bench = 10, FAAB budget = $100 — both configurable per-league, documented here as defaults, not
silently assumed.

## D8 — Team-season Monte Carlo simulation
`PRODUCT_SPEC.md` §Simulation says "eventually" and `ARCHITECTURE.md` calls it
"later-stage." Scheduled as M13 (after the validated core), not dropped.

## D9 — No third-party data committed to git
`ARCHITECTURE.md` §15 prohibits distributing proprietary source data without rights. `data/`,
`models/`, `predictions/`, `reports/`, `state/` are gitignored. Test fixtures are schema-accurate
synthetic data (same columns/types as real sources, invented values), never a copy of a real
snapshot — this also keeps the test suite fast and network-independent.

## D11 — Canonical spine is nflverse `players`; orphan draft/combine rows are quarantined, not minted as new players
Verified against real data: nflverse `players` has 25,046 rows, 100% populated and unique
`gsis_id` — a clean spine key. `draft_picks` and `combine` go back further (draft_picks to
1936) and include players who never made an NFL roster after being drafted, or combine
invitees who were never drafted; `combine` in particular carries **no `gsis_id` at all**
(verified against real data — only `pfr_id`/`cfb_id`). 229 of 12,927 `draft_picks` rows
reference a `gsis_id` not present in the `players` spine.

**Decision:** `players` (nflverse) is the single minting authority for `player_id`. A
`draft_picks`/`combine` row that cannot be matched to the spine via `gsis_id` or `pfr_id` is
recorded as an `identity_exceptions` row (`unmapped_draft_pick` / `unmapped_combine_prospect`)
rather than becoming a second, parallel ID-minting path. This keeps `player_id` minting
single-sourced and avoids two independently-generated ID spaces that could later collide.
Rookie modeling (M7) still gets full value from matched rows — 7,990 `cfb_player_id` and
6,131 `cfb_id` mappings were captured on first build — historically remote/unrostered
draftees are the ones quarantined, not the current/recent draft classes that matter for
rookie projection.

## D12 — DynastyProcess CSV exports use the literal string "NA" for missing values in every column, including ID columns
Verified against real data: `db_playerids.csv`'s `gsis_id` column has 4,483 rows with the
literal 3-character string `"NA"` (not a real null) — an R/readr export artifact that appears
across essentially every column, string and numeric alike (`sleeper_id` alone has 6,108). A
naive load would treat `"NA"` as a real (if bogus) ID value; since no real player has that ID,
a join would just silently fail to match rather than corrupt anything, but it's still wrong to
store `"NA"` in the crosswalk as if it were meaningful. Handled by passing
`nullstr=['NA']` to DuckDB's `read_csv_auto` for every CSV read in `identity/canonical.py`'s
`reader_expr()`.

## D13 — DynastyProcess's own crosswalk sometimes disagrees with itself
Verified against real data: `db_playerids.csv` contains real duplicate `gsis_id` values whose
other columns conflict — e.g. `gsis_id` `00-0031320` is mapped to both "Fred Williams" and
"Kevin Smith" on different rows; `00-0030653` ("Ray Agnew") appears twice with two different
`mfl_id` values and two different positions. This is a data-quality issue in the source
itself, not an artifact of joining it to something else.

**Decision:** any `gsis_id` that appears more than once in the DynastyProcess export is
treated as internally inconsistent and every row for it is excluded from the crosswalk
entirely (recorded as `ambiguous_source_mapping`) — never "pick whichever row loaded first."
The affected canonical player still exists (from the nflverse spine) and simply has no
DynastyProcess-derived IDs (sleeper_id, mfl_id, etc.) until a human resolves the exception.
28 such conflicts were found on first build, out of 12,472 crosswalk rows.

## D15 — as-of semantics and the source of game dates
nflverse publishes no separate `schedules`/`games` release tag (verified: both 404). Every
game's real calendar date lives in `pbp` (`game_id`, `game_date`) instead, so `games` is
derived from there (`features/games.py`), reading only the game-identifying columns.

`features_as_of(con, as_of_date)` (`features/panel.py`) filters `game_date < as_of_date`
(strict, not `<=`): a game's stats are only considered "known" starting the day *after* it
was played, which is the conservative choice given nflverse doesn't publish a same-day
stat-finalization timestamp. `player_week_features`'s lag columns are additionally leakage-
safe *by construction* (SQL window frames that structurally exclude the current and all
future rows), independent of this row-level filter — see tests/leakage/.

## D14 — Agents are deterministic services, not LLM calls
`ARCHITECTURE.md` §6: "The project orchestrator is an engineering orchestration layer, not itself
the source of fantasy truth." Agents in `src/alpha_squad/agents/` are typed Python
functions/classes producing `AGENT_CONTRACTS.md`-shaped results, orchestrated by a DAG scheduler.
No agent calls an LLM to produce a projection, ranking, or recommendation — all fantasy-relevant
output comes from the deterministic model/market/league modules those agents wrap.
