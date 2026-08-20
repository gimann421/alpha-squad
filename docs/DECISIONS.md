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

## D16 — Market snapshot join key and ADP-implied baseline scope
Verified against real data: `fp_ecr_history.id` (FantasyPros' own internal player ID) matches
`player_id_map`'s `fantasypros_id` (from the M2 DynastyProcess crosswalk) for 211,741 of
225,778 (93.8%) `ecr_type='ro'` rows — clearly the same ID space, and better coverage than
`cbs_id` (61.6%) or `yahoo_id`. `market_snapshot` joins on `fantasypros_id`, never on name.

`PRODUCT_SPEC.md` also calls for an "ADP-implied baseline where supportable." No independent
ADP (average live/mock draft position) series is reachable: FantasyPros ADP requires the
blocked API, and DynastyProcess's `values-players.csv` carries dynasty *value* (derived from
ECR itself), not a separate live-draft ADP. **Decision:** ADP-implied is LIMITED — ECR-implied
(D17) stands in as the closest available market-consensus-rank baseline; a genuine ADP-implied
baseline activates automatically once FantasyPros ADP is reachable, using the same
rank-to-points calibration mechanism.

## D17 — ECR-implied baseline uses a walk-forward rank-to-points calibration curve, not a hardcoded formula
FantasyPros ECR is a *rank*, not a points prediction, so turning it into a point value needs a
calibration step. Built by fitting the historical relationship between preseason ECR rank and
actual season points, per position, using only seasons strictly before the one being
predicted (expanding window) — never seasons after, which would leak the outcome being
predicted back into its own calibration curve. `ecr_type='ro'` (redraft-overall, 1QB) is used
for this general-purpose baseline; the 2QB-aware series (`rsf`/`dsf`) that fits the target
league (D7) is reserved for M8's EDGE engine, which needs the market-vs-model comparison to be
format-aware.

## D18 — Two established-player ML evaluations, not one, to keep the baseline comparison honest
M5's first working model (`models/established/train.py`) predicts weekly and aggregates to a
season total, using player_week_features rows *from the target season itself* (recent
trailing form) as inputs. Comparing that directly against M4's baselines — which predict
season S using only information from before S — would overstate ML's advantage, since the
weekly model has strictly more information available (it gets to see most of the season
before predicting the rest). **Decision:** keep both, clearly separated. `train.py`'s weekly
models answer "in-season rest-of-season update" (a real PRODUCT_SPEC.md output) and are not
compared head-to-head against M4. `models/established/season_level.py` is the genuine
apples-to-apples comparison: season S-1 aggregate + preseason ECR predicting season S,
exactly matching M4 baselines' information set.

## D19 — "ALL positions" evaluation must be scoped to fantasy-relevant positions, not literally every position
Real bug found during M5 review: `player_season_stats` contains every position that
accumulates any stat in `stats_player_week` — not just QB/RB/WR/TE, but also LB, CB, DT, DE,
OT, SAF, G, DB, K, C, P, LS, and more (2024: 1,512 total rows, only 592 at the four skill
positions the target league actually rosters). Hundreds of these non-skill-position players
correctly score ~0 PPR points, and every baseline correctly predicts ~0 for them too — so
pooling them into an "ALL positions" MAE contributes near-zero error from hundreds of
trivially-easy pairs, dragging the pooled metric down to a number that looked far better than
any individual skill position's real performance (verified: reported "ALL" MAE of ~14.7 for
2024 weighted-2yr, while every individual skill position's own MAE was 33-65). This was
silently wrong in every M4 evaluation report produced before the fix.

**Decision:** `models/evaluate.py`'s `SKILL_POSITIONS = ("QB","RB","WR","TE")` constant scopes
the `ALL` rollup to only these positions before computing pooled metrics. Per-position
(QB/RB/WR/TE) breakouts were never affected — they already filtered correctly — so no
prior per-position numbers need correction, only the "ALL" rows. `player_season_stats`
itself is left unscoped (still covers every position) since it is general-purpose storage
that a future capability might legitimately need; the fix lives in the evaluation layer,
where the fantasy-relevance judgment actually belongs. All M4/M5 evaluation reports were
regenerated after this fix. Regression-tested in tests/unit/test_evaluate.py.

## D20 — College production (cfbfastR) has no verified ID bridge to the rest of the identity graph; rookie model v1 scopes to draft capital + combine + landing spot
Verified against real data while building M7: `player_college_bridge.cfb_player_id`
(nflverse `draft_picks`) and `.cfb_id` (nflverse `combine`) are slug-style strings
(`"clifton-abraham-1"`, `"kendall-blanton-1"`). cfbfastR-data's play-by-play player columns
(`rush_player_id`, `reception_player_id`, `target_player_id`, etc.) are numeric ESPN-style IDs
(`"4685522"`) — a completely different namespace, with no shared key. Separately,
cfbfastR-data's `player_stats` dataset (despite the name) is raw play-by-play, not
pre-aggregated season totals — turning it into per-player college season production would
require both solving the ID-bridge problem *and* building touchdown-attribution logic
(touchdown events are a separate column not directly tied to the rush/reception row).

**Decision:** rather than bridge college production via a name+school+season fuzzy match
(the only fallback available, and a materially larger undertaking — proposing candidates into
the same `identity_exceptions` quarantine used elsewhere, at real engineering cost for a
signal that draft capital already substantially proxies for), rookie model v1 uses the
signals that are already cleanly ID-linked and required no new bridge: **draft capital**
(round/pick/team — already gsis_id-linked, direct columns on `players`), **combine athletic
testing** (forty/bench/vertical/broad_jump/cone/shuttle — bridged via `player_id_map`'s
`pfr_id`, the same path M3 used for snap counts), and **landing spot** (the drafting team's
*prior-season* pass rate/play volume from `team_week_features` — using prior season only,
never the rookie's own season, to avoid a leakage look-ahead). This is not a corner cut
silently: draft capital is well-established in fantasy analytics as the single strongest
individual predictor of rookie outcomes, precisely because it encodes the NFL's own
evaluation of college production, athletic testing, and landing-spot fit. College production
is marked LIMITED, not fabricated via a shaky join; cfbfastR-data remains verified reachable
(docs/DATA_SOURCES.md) and the play-by-play is available in full for a future session to
build the aggregation + fuzzy-match bridge properly.

## D14 — Agents are deterministic services, not LLM calls
`ARCHITECTURE.md` §6: "The project orchestrator is an engineering orchestration layer, not itself
the source of fantasy truth." Agents in `src/alpha_squad/agents/` are typed Python
functions/classes producing `AGENT_CONTRACTS.md`-shaped results, orchestrated by a DAG scheduler.
No agent calls an LLM to produce a projection, ranking, or recommendation — all fantasy-relevant
output comes from the deterministic model/market/league modules those agents wrap.
