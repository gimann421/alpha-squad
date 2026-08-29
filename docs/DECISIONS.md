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

## D21 — EDGE uses 'rsf' (redraft-superflex, horizon-matched to the single-season model); evidence_score is a disclosed neutral placeholder pending M9; the gating rule requires agreeing rank+points edges and a confidence floor
Real data verified while building M8: DynastyProcess's `fp_ecr_history` carries several
`ecr_type` series (`ro`, `do`, `rsf`, `dsf`, plus a few not used here), all of them overall
(cross-position) ranks, not per-position ranks. `rsf` (redraft-superflex/2QB) genuinely differs
from `ro` (redraft 1QB): real 2026 preseason data shows QBs occupying most of the top overall
`rsf` slots (rank 1-6 are QBs, then the first non-QB at rank 7), which is exactly what a 2QB
league should look like and `ro` does not produce. `rsf` history only goes back to 2021 in this
snapshot (verified: 2021-2026 preseason coverage, ~550-900 distinct ids/year), which caps how
many seasons can be walk-forward validated.

**Decision 1 — market series:** EDGE compares the M6 uncertainty model's single-season
point/top24-probability predictions against `rsf`, not `dsf` (dynasty-superflex) or
`dynasty_values.value_2qb`. The model predicts one season of points; `dsf`/dynasty value price
in a multi-year outlook (age curves, draft capital trajectory, etc.) the model was never asked
to produce. Comparing them would produce "edges" dominated by a horizon mismatch (e.g. a
rookie WR with modest year-1 production but high dynasty value would look like a false "market
undervalues" signal) rather than genuine model-vs-market disagreement. A dynasty-horizon EDGE,
blending `dsf`/`value_2qb` with real age curves, is left to M10's trade/roster logic, which is
the layer that actually reasons about multi-year value. `dynasty_values` (normalized from
`values-players.csv`, 97.6% real identity coverage) is built and stored now specifically so
M10 has it ready.

**Decision 2 — evidence_score:** M9 (the evidence engine) does not exist yet. Rather than omit
the field (breaking the `AGENT_CONTRACTS.md` Edge contract shape) or hard-code a value that
could silently gate every action once evidence scoring is real, `evidence_score` is fixed at a
disclosed neutral placeholder (0.5), reported in every `edge_snapshot` row and echoed in its
`reasons` for transparency, and explicitly excluded from the BUY/SELL/HOLD/WATCH gate. When M9
ships, it only needs to start writing a real score into the same column — no schema or contract
change required.

**Decision 3 — the hard gating rule** (`ACCEPTANCE_CRITERIA.md`: "a raw ranking discrepancy
cannot alone produce a strong EDGE"): `classify_action` in `market/edge.py` requires the rank
edge AND the points edge to agree in direction, AND both to clear a materiality threshold
(rank ≥ 15, points ≥ 15 PPR), AND model confidence (M6's real interval-width-derived
`confidence`, not a placeholder) to clear a 0.5 floor, before BUY/SELL. A rank gap with no
corroborating points gap, or a rank/points disagreement, or insufficient confidence, is capped
at WATCH; near-zero edges are HOLD (explicit "market and model agree," distinct from WATCH's
"edge exists but not actionable"). Literally regression-tested in
`tests/unit/test_edge.py::TestClassifyActionGatingRule`, and re-verified against real stored
`edge_snapshot` output in the live network test.

**Result, honestly reported either way (real data, `rsf`, 2022-2025 — 2021 has no training
season yet since `rsf` history itself starts in 2021):** the BUY cohort's mean outperformance
vs. market-implied points was positive in 3 of 4 scored seasons (+19.77, +15.07, +13.98 PPR in
2022-2024; n=36-47/season) and essentially flat in the most recent (-0.56 PPR, 2025, n=31) — a
genuine out-of-sample signal that the gated EDGE finds real, actionable market inefficiency in
most seasons, not a guaranteed edge every year. The SELL cohort moved the same direction as the
market's own eventual mistake (negative outperformance, i.e. the sold-off player really did
underperform market expectation) in 2022/2023/2024 (-47.00, -21.92, -18.32 PPR), and the wrong
direction in 2025 (+36.91 PPR, n=12). This is reported as-is in `docs/PROJECT_STATE.md`'s M8
summary, not suppressed or cherry-picked.
(Figures recomputed in M13 after fixing the postseason-game contamination bug described in
D28 below; the direction and general strength of the finding are unchanged from the original
M8-era numbers, but every per-season figure shifted slightly and the previously-reported
4-for-4 BUY sweep is now honestly 3-for-4. See D28 for why.)

## D22 — Evidence engine v1 implements only PRODUCT_SPEC.md's Strong tier, with real detectors on officially-sourced structured data; Medium/Weak are registered vocabulary for a manual-entry path
Consistent with D5 (no news/social API is reachable in this environment): PRODUCT_SPEC.md's
Medium tier (repeated beat observations, coach comments, one strong practice) and Weak tier
(highlight clips, generic praise, social media, speculative commentary) all require a text/news
source this environment cannot reach. Building fake detectors for them, or quietly omitting
them from the taxonomy, would either fabricate signal or leave
`ACCEPTANCE_CRITERIA.md`'s "Strong/medium/weak hierarchy is implemented" only partially true.

**Decision:** `evidence/taxonomy.py` registers the full three-tier vocabulary from
PRODUCT_SPEC.md, including Medium/Weak `event_type`s with no detector behind them. A human (or
a future integration) can still write a structured Medium/Weak event through the same
`record_event()` contract used by real detectors — the manual-entry path promised in the
original plan (Phase 0's Decision 5). Only the four Strong-tier `event_type`s that map cleanly
onto reachable nflverse data have real detectors (`evidence/events.py`): `depth_chart_promotion`
/`depth_chart_demotion`, `injury_own_status`/`injury_teammate_opportunity`, `roster_transaction`,
`usage_share_spike`/`usage_share_drop`. This mirrors D20's rookie-model precedent: build what is
real from reachable data, mark the rest LIMITED with the reason on record, never fabricate.

## D23 — evidence_score is a real, mostly-neutral-in-practice value for M8's preseason EDGE, not a placeholder; contradicting evidence vetoes BUY/SELL
With M9 shipping, `market/edge.py`'s `evidence_score` (previously a disclosed constant
placeholder per the original D21) is now computed for real from `evidence_events` via
`evidence/prior_update.py::evidence_score_for_action`. But M8's EDGE (D21) is anchored to
*preseason* market snapshots (`market_snapshot` rows from July/August, before the season being
predicted has played a single game), while every real evidence detector in `events.py` only
ever produces *in-season* events (week ≥ 2, dated after that season's Week 1). The honest
consequence, verified in `tests/unit/test_evidence.py::TestEvidenceScoreForAction`: a
preseason-anchored EDGE build will see **no** qualifying evidence for the season it is
predicting, so `evidence_score` comes back neutral (0.5) in the overwhelming majority of real
calls. This is not a bug or a disguised placeholder — it is the honest state of a
preseason-timed decision meeting an in-season-timed signal, and it is reported as such (D23's
regression test proves the mechanism computes a real, moved score when evidence genuinely
predates the cutoff, e.g. an offseason transaction).

**Decision on how evidence participates in the gate:** rather than *requiring* evidence to act
(which would make BUY/SELL nearly always WATCH, since preseason evidence coverage is
structurally sparse) or ignoring it entirely (contradicting PRODUCT_SPEC.md: "A strong signal
requires model discrepancy, market discrepancy, supporting evidence, and reasonable
confidence"), `classify_action` (`market/edge.py`) adds evidence as a **veto, not a
requirement**: neutral evidence (0.5, "nothing recorded") never blocks an otherwise-valid
BUY/SELL, but evidence that actively *contradicts* the action's direction
(`evidence_score < EVIDENCE_CONTRADICTION_THRESHOLD = 0.35`) forces WATCH. This keeps M8's
already-published, real historical validation numbers (docs/PROJECT_STATE.md's M8 summary)
unchanged — every one of those calls saw neutral evidence and clears the veto trivially — while
giving the mechanism genuine teeth once evidence timing and EDGE timing eventually overlap (a
future in-season EDGE variant, or M9 evidence recorded further in advance of a season). Literal
regression tests for the veto: `tests/unit/test_edge.py::test_contradicting_evidence_vetoes_an_
otherwise_valid_buy` / `test_neutral_evidence_does_not_block_an_otherwise_valid_buy`.

## D24 — nflverse `depth_charts` has two incompatible real historical schemas; the evidence engine detects and handles both
Verified against real data while building M9: nflverse's `depth_charts` release changed format
at some point before the 2025 season. Seasons 2015-2024 (verified: 2019, 2022, 2024) use an
explicit `week`-keyed schema (`season, club_code, week, game_type, depth_team, ..., gsis_id,
position, depth_position, ...`, one row per player per week, `depth_team` — a VARCHAR despite
holding integers — as the within-position-group rank). Seasons 2025+ use a near-daily
`dt`-keyed schema (`dt, team, player_name, gsis_id, pos_grp, pos_id, pos_name, pos_abb,
pos_slot, pos_rank, captured_at`, ~221 distinct timestamps across a season, `pos_rank` a real
INTEGER). Treating both as the same shape (the initial implementation's mistake, caught by a
real `BinderException: column "dt" not found` when running against 2019 data) would have
silently produced zero depth-chart evidence for every pre-2025 season.

**Decision:** `evidence/events.py::_depth_chart_entering` detects which schema a given season's
file uses (`"dt" in columns`) and normalizes both into the same (gsis_id, team, pos_abb,
pos_rank) shape before any diff logic runs, restricted to QB/RB/WR/TE (`pos_abb`/
`depth_position` IN ('QB','RB','WR','TE')) in both branches to keep the signal fantasy-relevant.
For the old week-keyed schema, "the depth chart entering week W" is defined as the filing for
week W-1 (there is no sub-week timestamp to compare against a game date, so this is the most
recent fully-known state strictly before W — conservative and leakage-safe, consistent with the
`dt`-based branch's own "strictly before the week's first game" rule). `depth_team` is
`TRY_CAST` to INTEGER since it is a VARCHAR column holding integer-valued strings.

## D25 — Replacement level is a real value-based-drafting (VBD) allocation over the league's own lineup config; dynasty trade's age curve is a disclosed heuristic, not a trained model; the M6 season-level model structurally excludes rookies, filled from M7's real predictions instead
`PRODUCT_SPEC.md`'s league optimizer requires replacement level, positional scarcity, and
marginal value over replacement to be real, not a fixed "top-N" assumption, and specifically
calls for the architecture to represent arbitrary league settings while exactly representing
the target league (10 teams, 2QB/2RB/2WR/1TE/2FLEX). `league/replacement.py` implements this as
a real VBD allocation: dedicated slots (QB, RB, WR, TE) are filled first by within-position
rank, then flex slots are filled by the single best remaining players across every
flex-eligible position (RB/WR/TE) -- earned by actual projected value, not split evenly by
position. Verified against real 2025 data: this produces 20 dedicated QB starters (10 teams x
2, matching the target league exactly) and a QB replacement level of ~220 points -- a
genuinely different, deeper market than a 1QB league's ~13-15th-ranked-QB replacement would be,
exactly the "strong test that the engine is real" the original implementation plan called for.

**Real player coverage gap found and fixed:** M6's season-level uncertainty model requires a
prior season's `player_season_stats` row (`load_season_level_data`'s join), which structurally
excludes true rookies -- verified against real data: 0 of 442 real 2024
`uncertainty_predictions` rows belonged to a `rookie_season=2024` player. Since rookies are
exactly the player class a waiver-wire or rookie-draft recommendation most needs,
`league/replacement.py::load_season_projections` fills any player missing from
`uncertainty_predictions` in from M7's real `rookie_predictions` (`draft_class == season`)
rather than silently omitting them -- established players always take the M6 value when both
exist (M6 has more information: an actual prior season), rookies are covered by the model
actually built for them.

**Dynasty trade's age curve is a disclosed heuristic, not a trained model:** no ground-truth
dynasty-value-decay dataset exists to fit one in the time/data available in this environment.
`league/trade.py::AGE_CURVE_PARAMS` (position-specific peak/decline/cliff ages, fantasy-analytics
convention) is documented as an assumption here, exactly like every other documented assumption
in this log, and every trade recommendation's `reasons` explicitly labels it as a heuristic, not
a validated signal -- the real, validated signals in a trade recommendation are M8's EDGE
action/reasons and the real DynastyProcess dynasty value; the age curve is a disclosed secondary
adjustment on top of them, never the primary basis for BUY/SELL (that stays M8's, unchanged).

**Waiver/FAAB bid must react to what just happened, not restate the preseason baseline:**
verified against a real case (Keon Coleman, a 2024 rookie WR real-promoted to WR1 by week 8):
his static, preseason-anchored M7 season-total projection is below replacement level (a
realistic outcome for many rookies at the time they're drafted), which would zero out a FAAB
bid under a naive marginal-value-only formula despite his real, detected
`depth_chart_promotion` and `usage_share_spike` evidence (M9) saying otherwise. `recommend_waiver_pickup`
blends a real evidence-driven "value-spike" contribution into the bid signal (bounded, scaled
to the league's own replacement-level magnitude) precisely so a confirmed recent role change can
justify a real bid even when the season-level baseline hasn't caught up -- exactly
`PRODUCT_SPEC.md`'s "value-spike probability" requirement, and exactly what a real waiver-wire
decision needs to weigh.

## D26 — The orchestrator's concurrent task dispatch must not run schema DDL per-connection; agents are thin wrappers around already-validated M1-M10 code, not new logic
Building M11's DAG orchestrator surfaced a real DuckDB concurrency bug during its own test
suite, not a hypothetical one: `run_pipeline`'s original per-task connection factory called
`init_db()` (which issues `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS`) on every worker thread's own connection. When two independent tasks became READY and
started concurrently (exactly the real-parallelism case `test_independent_tasks_run_concurrently`
exists to prove), two threads issued DDL against the same on-disk file at once and DuckDB raised
a real `TransactionException: Catalog write-write conflict on alter with "players"` — this is
not a theoretical risk description, it is what actually happened during review.

**Decision:** `init_db()` runs exactly once, synchronously, in the setup phase before any
worker thread opens a connection; per-task connections opened during the run assume the schema
already exists and never issue DDL. Real per-task DB reads/writes (via `agents/state.py`) are
still serialized through a shared lock (`_db_lock`) for the same underlying reason — DuckDB's
single embedded file does not support safe unserialized concurrent writes across connections.
This means M11's "independent tasks run in parallel" claim is honest about what is actually
concurrent: the scheduling/readiness logic and each agent's own non-DB work (e.g. HTTP fetches
in `data_engineering`) genuinely overlap across threads (verified: two real 0.3s stub tasks
start within 0.2s of each other), while DB commits are serialized for correctness — not a fake
"parallel" that is secretly sequential, and not an unsafe "parallel" that would corrupt state
under real concurrent DDL.

**Agents wrap, they do not re-implement:** every agent in `agents/registry.py` is a thin
function calling the exact M1-M10 functions already built and validated in their own
milestones (`build_identity`, `run_established_ml`, `run_edge_build`, `recommend_draft_pick`,
etc.) — no agent contains new modeling or business logic. `evaluation_qa`'s REJECT capability
(ACCEPTANCE_CRITERIA.md: "Evaluation/QA can reject unsupported claims") reuses M5's own real
`model_registry.validated` gate rather than deriving a new judgment. The disagreement protocol
(`agents/disagreement.py`) reuses M8's real, already-computed `edge_snapshot.rank_edge` for
model-vs-market conflicts and M4/M5's real, already-computed `evaluation_results.mae` for
baseline-vs-ML conflicts — real, stored data, not fabricated comparisons. Verified against real
2024/2025 data: 292 real model-vs-market rank disagreements and 4 real baseline-vs-ML
disagreements (the established-ML ensemble beats the ECR-implied baseline's MAE by roughly 3x
at every position, consistent with M5's own already-published results) were detected and
recorded, preserving both positions per AGENT_CONTRACTS.md's conflict protocol.

## D27 — The API is a pure projection layer (every response field traces to an already-persisted table or an M10 function call); the frontend is deliberately lean but genuinely live, verified in a real browser
`ARCHITECTURE.md`/`ACCEPTANCE_CRITERIA.md` require the application layer to expose validated
player intelligence without duplicating or bypassing core model/decision logic, and require a
test proving UI endpoints return engine output with no parallel path — killing the engine must
break the UI, not silently serve stale demo data.

**API layer (`src/alpha_squad/api/`):** every route in `api/routers/*.py` is either (a) a
`SELECT` against an already-computed, already-tested table (`uncertainty_predictions` M6,
`rookie_predictions` M7, `edge_snapshot` M8/M9, `evidence_events` M9, `source_health_log` M1),
with the response schema's fields mapped one-to-one from the query's own SELECT list, or (b) a
direct call into the exact M10 function the CLI calls (`recommend_draft_pick`,
`recommend_waiver_pickup`, `recommend_dynasty_trade`) — never a re-implementation. `/provenance/
{id}` performs a plain lookup across every table that could own an ID, again no new
computation. `RankingRow` was extended to carry `prediction_id` (initially omitted) so a
ranking can actually be traced back to its source row through `/provenance` — found during this
milestone's own review while writing the live traceability test.

**Verified in a real browser, not just asserted:** using the pre-installed Chromium via
Playwright, the React dev server was loaded, all six views were clicked through and screenshot
against the real persisted DuckDB (real players — Lamar Jackson, Tyler Conklin, Amari Cooper —
with correct EDGE reasons, evidence events, and BLOCKED/NO_CREDENTIALS source badges rendering
honestly), a draft recommendation was submitted end-to-end through the real form and matched
the CLI's own output for the same inputs, and — the literal Gate 8 test — the API process was
killed and the page reloaded: the UI surfaced a real fetch error ("Couldn't reach the Alpha
Squad API"), not fabricated or stale content. The first draft of that error string literally
said "as intended" (written for this decision log, not for a user) and was caught and rewritten
during the same review pass.

**Frontend scope, deliberately:** `ARCHITECTURE.md`/`IMPLEMENTATION_PLAN.md` describe the web
SPA as "presentation only, zero business logic" — a materially lower correctness bar than the
modeling/decision layers. The React+Vite+TS app (`web/`) is real and live (six views: Rankings,
EDGE, Rookies, Evidence, League, Source Health; every view fetches from the real API, no mock
data, no client-side scoring), but is intentionally not a polished production UI — that tradeoff
matches where PRODUCT_SPEC.md's own rigor requirements are concentrated (data/model/decision
correctness), not frontend polish.

**Tooling note:** `ruff`'s B008 rule (flags a function call in an argument default) is a false
positive for FastAPI's own idiomatic `Depends(...)`/`Query(...)`-in-signature pattern — FastAPI
inspects these at route-declaration time, not per-request, so it isn't the mutable-default bug
the rule exists to catch. Disabled via a `per-file-ignores` entry scoped to `src/alpha_squad/
api/**/*.py` only, not project-wide.

## D14 — Agents are deterministic services, not LLM calls
`ARCHITECTURE.md` §6: "The project orchestrator is an engineering orchestration layer, not itself
the source of fantasy truth." Agents in `src/alpha_squad/agents/` are typed Python
functions/classes producing `AGENT_CONTRACTS.md`-shaped results, orchestrated by a DAG scheduler.
No agent calls an LLM to produce a projection, ranking, or recommendation — all fantasy-relevant
output comes from the deterministic model/market/league modules those agents wrap.

## D28 — `player_week_stats`/`team_week_stats` silently mixed postseason games into every "season" aggregate since M3; fixed at the source and the affected tables rebuilt and retrained
Found while building M13's team-season simulation: KC's simulated 2024 season had a rookie WR
(Xavier Worthy) drastically outscoring Patrick Mahomes, traced back to his *real* 2024 season
total including 3 playoff games plus a Super Bowl outlier performance, extrapolated as if it
were a normal-game rate. `nflverse`'s weekly stat releases (`stats_player_week`,
`stats_team_week`) include postseason weeks with no flag of their own; `games` (built from
`pbp`, features/games.py) already carries the real `season_type` field as `game_type`, but
neither `features/player.py::build_player_week_stats` nor `features/team.py::build_team_week_stats`
filtered on it before joining. Every "season" aggregate built on top —
`player_season_stats` (feeds M4's previous-year/weighted-2yr/per-game-rate baselines),
`player_week_features`'/`team_week_features`'s trailing "last 3 games" windows (which could
silently pull a playoff game in as one of a team's "last 3" games heading into the next
season) — inherited the contamination for every team that made the playoffs, in every ingested
season (2015-2025), not just M13's new code.

**Fix:** `build_player_week_stats` and `build_team_week_stats` now join `games` with
`AND g.game_type = 'REG'`; `models/simulation/team_scores.py::build_team_week_points` filters
`pbp`'s own `season_type = 'REG'` directly. This stops future ingestion from reintroducing the
problem. The already-populated tables needed an explicit `DELETE` (an `INSERT ... ON CONFLICT
DO UPDATE` upsert does not remove keys the new query stops producing) — removed 8,543 stale
rows from `player_week_stats`, 266 from `team_week_stats`, matching row-for-row the count
`features build`'s corrected query itself produced.

**Blast radius and what was redone:** this table feeds M4 (baselines), M5 (established ML
features and targets), M6 (uncertainty/calibration), M7 (rookie features depend on
`team_week_stats`), M8 (EDGE, via `player_season_stats`), and M13. All of `alpha-squad features
build`, `evaluate baselines`, `train established`, `train established-season`, `train
uncertainty`, `train rookie`, `edge build`, and `edge validate` were re-run against the cleaned
tables (no new network fetch needed — snapshots were already cached locally). Model structure
and the qualitative findings (ML beats baselines by a wide margin at every position; EDGE's BUY
cohort beats market expectation in most seasons) are unchanged; the exact numbers shifted
slightly. D21's EDGE validation paragraph above was updated with the corrected figures rather
than left stale. `docs/TRACEABILITY.md` and `reports/*.md` reflect the post-fix numbers.

A regression test (`tests/unit/test_features.py::test_build_player_week_stats_excludes_postseason_games`
and the team-stats equivalent) asserts a synthetic postseason game's stats never reach
`player_week_stats`/`team_week_stats`, so this cannot silently regress.

## D29 — Team-season Monte Carlo: the QB is anchored to the same `pass_attempts` draw as his pass-catchers, and every position's target/carry share is normalized against the team's real total volume, not the sum of only the "qualifying" players
Verifying M13's `models/simulation/correlated.py` (docs/DECISIONS.md D8's deferred simulation
item) against real data surfaced two further, unrelated bugs beyond D28's postseason
contamination — both caught by checking `qb_wr1_correlation` and player-level season totals
against known real outcomes rather than trusting that the code ran without error.

**Bug 1 — QB anchored to the wrong shared variable.** The first version computed the
QB's simulated weekly points as `team_points * (real fantasy points per team point)`, while
WR/TE/RB were `pass_attempts * share * efficiency`. Both `team_points` and `pass_attempts` come
from the same per-trial joint draw, so this should still correlate the QB with his
pass-catchers — but real per-team history (checked directly: KC pre-2024,
`corr(pass_attempts, team_points) = -0.09`) shows those two dimensions are only weakly (and
sometimes negatively) related, because of ordinary game-script effects — a team already
winning big tends to run more and pass less. The result was measured, not assumed:
`qb_wr1_correlation` came back at -0.03, essentially zero, the opposite of the property the
module exists to demonstrate. Real QB/WR1 fantasy correlation comes specifically from sharing
the same passing plays (a TD pass scores both players from the same snap), so the QB is now
anchored to `pass_attempts * (real fantasy points per pass attempt)` — the same shared draw
every pass-catcher already uses, and the same functional form used for every other position.
Verified afterward across all 32 teams x 3 seasons (2022-2024, 96 simulations):
`qb_wr1_correlation` positive in 100% of runs (mean 0.358, range 0.27-0.46, std 0.038) — a
real, empirically-measured result, not a hardcoded one.

**Bug 2 — target/carry share's denominator didn't match what it was later multiplied
against.** `_pass_catcher_shares` computed each qualifying WR/TE's share as
`player_targets / sum(qualifying WR/TEs' targets)`, then multiplied that share by
`pass_attempts` — the team's *total* simulated pass volume, which also covers targets to RBs
and to receivers below the `MIN_PLAYER_WEEKS` qualification floor. Caught by a real-data sanity
check: DET's real 2024 WR1 (Amon-Ra St. Brown, a real, elite 316 PPR-point season) simulated to
a 504-point mean — traced to a share denominator (404, sum of qualifying WR/TE targets only)
roughly two-thirds the size of the team's real total targets (522), inflating every qualifying
pass-catcher's implied volume by about the same ratio. Fixed by computing share against the
team's real total targets that season (all positions, all players) — the same basis
`pass_attempts` represents — mirrored for `_rb_shares` against team total carries. Re-checked
against the same DET case: 504 -> 395 (residual gap from using the prior season's environment
distribution as the volume base and the lognormal noise term's mean-inflation, both intentional
design choices, not a further bug).

**Also fixed in the same pass:** `team_week_points` (D8/M13's own new table, built by
`models/simulation/team_scores.py`) had only ever been built for [2023, 2024] as an initial
smoke-test range, so `_team_environment_history`'s `season < before_season` filter silently
starved every simulated season except 2024 of any real history at all (`simulate_team_season`
returned `None` for e.g. SF 2023 purely for this reason, not from a genuine data gap — SF had
8 real prior seasons in `team_week_stats`, just none yet in `team_week_points`). Backfilled to
the full ingested 2015-2025 range to match `team_week_stats`/`player_week_stats`.

**Bug 3 — the seeded RNG stream was not actually reproducible, caught by writing the
reproducibility test rather than assuming it would pass.**
`tests/unit/test_simulation.py::test_same_seed_is_bit_for_bit_reproducible` initially failed:
two calls to `simulate_team_season` with an identical `seed` produced identical
`mean_team_points` and identical QB output, but slightly different WR1/WR2 output (and
therefore a different `qb_wr1_correlation`) between runs. Root cause: `_pass_catcher_shares`/
`_rb_shares` return a `dict` built from a SQL `GROUP BY` query with no `ORDER BY`, and
`simulate_team_season` iterates that dict, drawing each player's `rng.lognormal(...)` noise
sequentially from one shared `np.random.Generator` — DuckDB's `GROUP BY` output order is not
guaranteed absent an explicit `ORDER BY`, so which named player consumed which slice of the
seeded RNG stream was query-plan-dependent, not code-dependent. Fixed with an explicit
`ORDER BY player_id` on both queries, plus a `, s.player_id` tiebreaker added to
`_starting_qb`'s existing `ORDER BY count(*) DESC` for the same reason (two QBs tied on real
start count would otherwise be a second source of the same class of bug). Verified after the
fix: 3 repeated real calls against KC 2024 (`seed=42`) produce bit-identical
`mean_team_points`, `qb_wr1_correlation`, and every player's `mean_points` to full float
precision.

## D30 — README, Makefile, and CI had drifted from the real CLI/system as it was built out; fixed while writing docs/TRACEABILITY.md rather than documenting the drift as a limitation
Writing `docs/TRACEABILITY.md`'s "Engineering quality" section against
`ACCEPTANCE_CRITERIA.md`'s "README documents setup and workflows" / "Tests run
automatically/continuously" checkboxes surfaced three real, independently-discovered gaps —
none related to D28/D29's data bugs, all found by checking the actual claim rather than
assuming it still held from M0:

1. **`README.md` was the original planning package's own meta-README** ("This directory is
   the definitive implementation package...", "Recommended startup: 1. Put this package into
   the repository...") — accurate when M0 started from an empty repo, but never replaced once
   Alpha Squad was actually built, so it documented how to *hand this package to a Claude Code
   session*, not how to install, run, or use the system that session built. Rewritten to
   document the real thing: `make install`/`test`/`lint`, the real pipeline order
   (`ingest`→`identity`→`features`→`market`→`train`→`evaluate`→`edge`→`simulate`→`orchestrate`→
   `serve`), the real CLI tree, and a map of `docs/*.md`.
2. **`Makefile`'s `train` and `evaluate` targets were broken** — `alpha-squad train
   --walk-forward` and `alpha-squad evaluate --compare-baselines` were sketched in the
   original implementation plan's verification-command list before the CLI existed, and were
   never updated once M4/M5 built the real subcommands (`train established-season`, `train
   uncertainty`, `train rookie`, `evaluate baselines`). Verified broken by literally running
   them (`No such option: --walk-forward`) rather than assuming; every replacement command in
   the fixed Makefile was individually run and verified working during this same milestone's
   retrain pass. Added `market`, `edge validate`, `simulate`, and `orchestrate` targets, which
   had no Makefile entry at all despite being real, working CLI surfaces since M8/M11/M13.
3. **No CI existed** — only local `make test`/`make lint`. Added
   `.github/workflows/ci.yml`: checkout, `uv python install 3.12`, `make install`, `make
   lint`, `make test` (offline suite only — network-marked tests need real external source
   access this runner won't have, consistent with `pytest`'s own default marker exclusion).
   Validated the YAML directly (`yaml.safe_load`) rather than assuming it was well-formed;
   caught and fixed the classic YAML 1.1 "Norway problem" in the process (`on:` unquoted
   parses as the boolean `true`, not the string key `"on"` — GitHub's own workflow parser
   special-cases this and it would likely have worked unquoted regardless, but `"on":` removes
   the ambiguity at zero cost rather than relying on that).

Discovered a fourth, related gap while validating the new CI job would actually pass: `make
lint` runs both `ruff check` (clean) and `ruff format --check` — the latter failed on 31 files,
almost all pre-existing (from M8-M12, not touched this session), so this drift predates M13 and
had simply never been caught because no CI ever ran `make lint` end to end and `ruff format
--check` was never re-verified after `ruff check` alone came back clean. Fixed by running `ruff
format src tests`; diffed the result to confirm every change was pure line-wrapping/whitespace
(spot-checked `api/routers/league.py`'s largest diff) and re-ran the full offline suite (still
204 passed) to confirm no behavior changed. Both `ruff check` and `ruff format --check` are now
clean, matching what `docs/TRACEABILITY.md`'s "Ruff/static checks pass" row claims.

## D31 — Re-verified 2026-08-22: this environment's network egress policy changed. Sleeper is now genuinely AVAILABLE; FantasyPros/CFBD are network-reachable and blocked only on missing credentials
CLAUDE.md's own instruction is to re-verify with `alpha-squad sources status` before assuming
D3's environment snapshot is still current, rather than treat it as permanent. Asked to
"check the env again" and then "now try," re-ran the real checks — `alpha-squad sources
status`, the proxy's own connection log, and direct unauthenticated calls to each adapter's
real production endpoint (not just a bare domain root, which can misleadingly redirect/succeed
without exercising the actual code path) — rather than repeating the D3-era conclusion from
memory.

**Real result, verified via actual data returned, not just a status code:**
- **Sleeper (`api.sleeper.app`) is now fully AVAILABLE, no credentials needed.**
  `sources status` returned real data: `state` (1 real row), `players` (the real ~12k-player
  pool), `trending_adds`/`trending_drops` (25 real entries each). The health check's
  `league`/`league_rosters` calls use a placeholder `league_id=0` (`sleeper.py`'s
  `default_health_params`) and correctly 404 against Sleeper's real API since no such league
  exists — not a policy block; `league_drafts` for that same fake ID succeeded with an empty
  list, confirming the endpoint itself works fine. A real league ID would pull real league
  state.
- **FantasyPros and CFBD's real production endpoints are now network-reachable too** — called
  each directly, unauthenticated: FantasyPros returned a clean `{"message":"Forbidden"}` (a
  real API auth rejection, not a connection failure), and CFBD returned its own detailed real
  message ("Unauthorized. Did you forget to add \"Bearer \" before your key?... register for
  your free API key"). Both `sources status` still reports these `NO_CREDENTIALS` because the
  adapters intentionally never attempt a call without a configured key (`SourceCredentialsError`,
  D3/CLAUDE_CODE_LEAD_PROMPT.md §8) — that check happens before the network call, so it can't by
  itself distinguish "still policy-blocked" from "just needs a key." The direct unauthenticated
  probe is what actually establishes the network layer is open now.
- **KeepTradeCut's bare domain now returns HTTP 200** (previously blocked at CONNECT), but no
  adapter exists for it in this codebase — D3's original decision to cover its role entirely via
  DynastyProcess's dynasty values stands unchanged; there is nothing to activate.
- **ESPN's bare domain now returns a real app-level 403** (a WAF/bot-defense response, not a
  network block) — still not a required source, so left as-is.
- **`api.github.com`** is reachable at the network layer, but real repo calls 403 with a Claude
  Code Remote session-scope message (this session's GitHub access is scoped to specific attached
  repos, unrelated to the egress policy) — irrelevant either way since the project only ever
  reads `raw.githubusercontent.com` release-asset URLs directly, confirmed working throughout.

**What this changes:** `docs/DATA_SOURCES.md` updated to reflect Sleeper as AVAILABLE and
FantasyPros/CFBD as credential-gated rather than policy-blocked. `ACCEPTANCE_CRITERIA.md`'s
"Sleeper integration works or limitation is explicitly documented" now reads MET rather than
BLOCKED in `docs/TRACEABILITY.md`. No source code changed — every adapter was already built to
activate unchanged the moment its blocker cleared (D3's own stated design intent), and that
held up exactly as intended.

**What this doesn't change on its own:** nothing in the pipeline currently *calls* Sleeper for
anything beyond the health check — league/roster/draft state is still read from the local YAML
config (D6), and the identity crosswalk's `sleeper_id` role was already filled by
DynastyProcess. Wiring Sleeper in for something it would newly add value on — e.g.
`trending_adds`/`trending_drops` as a real, timestamped, community-momentum evidence signal
(PRODUCT_SPEC.md's Weak tier explicitly includes "social media"/buzz-type signals, previously
undevelopable per D5/D22 since no such source was reachable at all), or real per-league sync
given an actual Sleeper league ID — is a deliberate product decision about what to build next,
not implied by the source becoming reachable, and is left for direction rather than assumed.

## D32 — Sleeper trending adds/drops wired in as the first real Weak-tier evidence signal; fixed a real preseason evidence-cutoff bug found while verifying it against real data
Following D31's finding that Sleeper is genuinely reachable now, built the trending-momentum
signal flagged there as a real opportunity: `evidence/sleeper_trending.py::detect_sleeper_trending`
fetches Sleeper's real `trending_adds`/`trending_drops` (no auth), resolves each entry to a
canonical `player_id` via DynastyProcess's `sleeper_id` crosswalk (already in `player_id_map`
since M2), and records each as a `social_media_buzz` event (PRODUCT_SPEC.md's Weak tier,
registered but undevelopable since D5/D22 — this is its first real detector) via the existing
`record_event()`/taxonomy machinery, direction +1 for an add and -1 for a drop.

**Kept architecturally separate from `evidence/events.py`'s four detectors, deliberately:**
those reconstruct evidence for an arbitrary *past* week from already-ingested nflverse
snapshots (pure over stored data, no network I/O). Sleeper's trending endpoints have no
lookback API — every call returns only *current* activity — so this module fetches live
itself and always represents "evidence as of right now," attributed to whichever (season,
week) the caller specifies. `week=1` is the natural choice before a season starts.

**Verified against real data, not assumed:** real Sleeper IDs resolved to real players
(Xavier Hutchinson, Barion Brown, Darren Waller, ...) via the real crosswalk; 48 of 50 real
trending entries resolved on a real run (2 presumably not yet in the identity graph). Offline
unit tests (`tests/unit/test_sleeper_trending.py`) mock `httpx.get` with the exact real
response shape (`[{"count": int, "player_id": str}, ...]`) verified against the live API
first, not a guessed shape. Live tests
(`tests/integration/test_sleeper_trending_live.py`) hit the real endpoint.

**Real bug found and fixed while verifying this against real data (not in the new code —
in `evidence/prior_update.py::evidence_score_for_action`, which every prior milestone had
already shipped and tested, just never with evidence dated in August):** its own docstring
promises evidence "recorded before that season's own Week 1" counts toward EDGE's evidence
score, but the code hardcoded `f"{season}-08-01"` as the cutoff. Real NFL Week 1 dates
(checked directly: 2023-09-07, 2024-09-05, 2025-09-04) fall in the first week of September,
not August 1st — so roughly five real weeks of preseason evidence, the entire training-camp
window, were being silently excluded from ever reaching EDGE, contradicting the function's
own documented intent. This had never surfaced before because no evidence source had ever
produced real events dated in August — Strong-tier detectors are in-season only (D23), and
nothing else existed at that horizon until this signal did. Fixed to use the season's real
Week 1 game date from `games` when ingested, falling back to September 1st (not August 1st)
only for a season with no games yet — exactly this case, a genuinely current/future season.
Two regression tests added to `tests/unit/test_evidence.py`
(`test_august_evidence_counts_when_no_real_week1_date_is_known`,
`test_real_week1_game_date_takes_priority_over_the_fallback`); the three pre-existing tests in
`TestEvidenceScoreForAction` still pass unchanged (their fixture dates never fell in the
August 1-September 1 gap this fix actually changes behavior for).

**A second real finding, from the same verification pass, that is not a bug:**
`test_real_trending_evidence_moves_the_edge_evidence_score` initially failed — the first real
trending-add player selected by the test also appeared, on the same real run, in
trending-drops (different real Sleeper managers making opposite moves on the same player,
live). Two WEAK (0.2) opposite-direction events legitimately cancel to a neutral aggregate
score, which is correct: real, simultaneous, conflicting community sentiment should score as
"no clear lean," not be forced to pick a side. Fixed the test to select a player with
unambiguous evidence rather than changing the (correct) aggregation behavior.

**Also updated:** `tests/integration/test_sources_live.py`'s
`test_sleeper_is_blocked_by_environment_policy` — which had explicitly anticipated exactly
this scenario in its own docstring ("If this test starts failing because Sleeper suddenly
*works*, that's good news — update docs accordingly and relax this assertion") — renamed to
`test_sleeper_is_really_reachable` and rewritten to assert success.

**Still not built:** real per-league Sleeper sync (replacing `target_league.yaml`'s assumed
defaults with a real league's actual settings) — needs a real Sleeper league ID, not supplied
yet.

## D33 — Multi-league support: a registry-based `resolve_league()` replaces every hardcoded single-league-file assumption; Sleeper leagues hydrate live, never drift out of sync
The user has multiple real leagues and asked to switch between them seamlessly. Investigated
the existing single-league assumption first rather than guessing at scope: `api/routers/
league.py`'s `{league_id}` URL parameter *looked* like it already supported multiple leagues,
but `_league_or_404` always called `load_league_context()` with no arguments (always the one
hardcoded `target_league.yaml`) and only ever checked whether that one config's own id
happened to match the URL — every other `league_id` 404'd unconditionally. Multi-league
support did not exist; only its shape did.

**Design:** `config/league_configs/registry.yaml` is the index — `{league_id: {source: yaml,
path: ...}}` or `{league_id: {source: sleeper, sleeper_league_id: ...}}`. `league/
context.py::resolve_league(league_id, *, con=None, settings=None, registry_path=...)` looks a
league up and dispatches: `source: yaml` calls the existing `load_league_context(path)`
completely unchanged (zero behavior change for anyone already using it directly); `source:
sleeper` calls the new `league/sleeper_context.py::load_sleeper_league_context`, which
re-fetches the real league from Sleeper's API on every call — a Sleeper league's settings can
never drift out of sync with what the league admin actually has configured, unlike a YAML
snapshot someone forgot to update after a scoring-settings change. `resolve_league()` with no
argument resolves to `target_league`, so this is purely additive: every pre-existing call site
that only ever knew about the one hardcoded file keeps working identically (verified:
`resolve_league() == load_league_context()`, byte-for-byte).

**Wired everywhere a league was previously hardcoded:** all 4 `league_app` CLI commands
(`--league <id>` replacing `--league-config <path>`), a new `alpha-squad league list`
command, `agents/registry.py`'s `run_fantasy_strategy` (task param `league` replacing
`league_config`), and the API's `_league_or_404` — which now actually uses the URL's
`league_id` for the first time, plus a new `GET /league` listing endpoint. The frontend's
`LeagueView.tsx` replaced its hardcoded `LEAGUE_ID` constant with a real `<select>` populated
from `GET /league`, remembering the last choice per-browser via `localStorage` (a viewer
convenience, not shared/synced state).

**Sleeper hydration (`league/sleeper_context.py`), mapped from Sleeper's documented public
API** (`settings.type` 0/1/2 → redraft/keeper/dynasty; `roster_positions` counted into
dedicated lineup slots + registered flex slots + bench/IR/taxi; `scoring_settings.rec` →
PPR; `settings.waiver_budget` → FAAB): a real, previously-undetected mismatch surfaced by
this milestone's own offline test, not live data — `FLEX_ELIGIBILITY` (context.py) registered
`"SUPERFLEX"`, but Sleeper's real `roster_positions` spelling is `"SUPER_FLEX"` (with an
underscore), so a superflex slot would have silently landed in `dedicated_slots()` (treated
as its own one-off position) rather than `flex_slots()`. Added `"SUPER_FLEX"` to
`FLEX_ELIGIBILITY` alongside the existing entry (additive, not a rename, so nothing already
relying on the unspaced spelling breaks). An `unrecognized_flex_slots` field on the hydrated
`LeagueContext` is the safety net for any *other* real Sleeper flex variant not yet
registered — flagged, never silently dropped — and the live test
(`tests/integration/test_sleeper_league_context_live.py`) asserts that list is empty against
a real league, specifically to catch exactly this class of mismatch against real data once
one is available.

**Honesty about verification status:** the Sleeper field mapping above is built from
well-documented, stable public API knowledge and thoroughly unit-tested against a realistic
mocked response (`tests/unit/test_sleeper_league_context.py`), but — unlike everything else
in this codebase — has *not yet* been run against a real Sleeper league, because no real
league id was available at implementation time. `tests/integration/
test_sleeper_league_context_live.py` is written and ready, reading a real league id from
`ALPHA_SQUAD_TEST_SLEEPER_LEAGUE_ID` and skipping cleanly without one (there is no way to
discover a real league id on our own — Sleeper has no public "any real league" listing
endpoint). This decision entry, `docs/TRACEABILITY.md`, and `docs/PROJECT_STATE.md` will be
updated with the real result once a real league id is supplied and this live test actually
runs — until then, `source: sleeper` registry entries are implemented-but-unverified, the
same honest status this project gives every source before its first real-data check.

## D34 — D33's Sleeper field mapping live-verified against two real leagues; both registered

The user supplied two real Sleeper league ids. `tests/integration/test_sleeper_league_context_live.py`
run against both, for real:

- `1395093181141381120` ("Dilworth"): 12-team redraft, 1QB, PPR, 2 FLEX, 5-man bench, $200 FAAB.
- `1326428555382394880` ("The Boys of Fall"): 10-team dynasty, 2QB/superflex, PPR, 2 FLEX,
  15-man bench, $100 FAAB — structurally close to `target_league.yaml`'s assumed defaults.

Both passed cleanly, including `unrecognized_flex_slots == []` — the specific check D33 flagged
as unverified. This confirms the `SUPER_FLEX` fix (and the rest of `FLEX_ELIGIBILITY`) against
real data, not just the documented API shape. Both are now registered in
`config/league_configs/registry.yaml` as `source: sleeper` entries (keys `dilworth`,
`boys_of_fall`), hydrated live on every call exactly like `target_league`. `source: sleeper`
registry entries move from "implemented-but-unverified" to verified as of this entry.

## D35 — Real API key values were committed to `.env.example` on `main`, in a public repo; rotated the intent (fixed the file; key rotation itself is on the user), added a durable guardrail

The user asked where to put `FANTASYPROS_API_KEY`/`CFBD_API_KEY` and was told: a local
gitignored `.env`, or this deployment's own env-var configuration — never a tracked file. They
instead added real values directly to `.env.example`, which is deliberately the one `.env.*`
pattern `.gitignore` carves back out as tracked (it is the template other contributors copy
from). The values were committed (`aea0be4`, directly to `main`, outside this branch) and
pushed. This repo is public, so both keys were live-exposed on the public internet from that
push until the fix below — real-world credential scanners routinely pick up exactly this
pattern within minutes, so the values must be treated as compromised regardless of any repo
cleanup.

Fix, with the user's explicit go-ahead (pushing to `main` is outside this project's designated
branch and requires it): a follow-up commit (`aa9e841`) restored the two lines to empty
placeholders, byte-for-byte matching the pre-leak version (diffed against the merge commit to
confirm no other drift). Push straight to `main` was fast-forward-safe (`aa9e841` descends from
the branch's merged tip via the earlier PR's merge commit), so no history rewrite was needed for
the file fix itself. The user was offered, and declined, a full `git filter-repo` + force-push
history purge — a strictly more invasive operation than removing the live value (it rewrites
shared history and would have orphaned every existing clone, including this session's own),
and one that still would not undo the actual exposure; rotating the key at the provider is the
only real remediation, which the file fix cannot do on the user's behalf. The user was told
directly, more than once, to rotate/regenerate both keys at FantasyPros and CFBD; whether they
have is outside what this repo can verify.

This project's designated branch (`claude/alpha-squad-plan-qhpg3r`) was then restarted from the
fixed `main` tip per this session's own merged-PR-branch-restart rule, rather than left pointing
at the pre-fix commit.

Durable guardrail added directly in `.env.example` (not just this log entry, so it survives
independently of any one session's memory): an explicit comment stating the file is tracked,
real values must never go here, and pointing at this entry.

## D36 — Re-verified 2026-08-23 in a fresh container: `CFBD_API_KEY` is live and confirmed AVAILABLE; `FANTASYPROS_API_KEY` is present but rejected by FantasyPros's own API, not a policy block

D31 predicted this exact follow-up (both keys network-reachable and blocked only on credentials)
and PROJECT_STATE.md's "Still not built" section explicitly flagged this as "pending confirmation
from a fresh session" since an env-var change in this deployment's config only takes effect for a
new container, not one already running. This session is that fresh container: `printenv` confirms
both `FANTASYPROS_API_KEY` and `CFBD_API_KEY` are set (values not printed), and `alpha-squad
sources status` was re-run to check what actually happens with them.

**CFBD: genuinely AVAILABLE, real data confirmed.** `teams` (1931 rows) and `player_usage` (5197
rows) returned real data immediately. `recruiting_players` initially errored `400 Bad Request`
("year required when team not specified") — not a credentials or policy issue, just a pre-existing
gap in `CfbdSource.default_health_params` (only `player_usage` passed a `year`). Fixed
(`sources/cfbd.py`) to also pass `year=2025` for `recruiting_players`; re-ran and got 4120 real
rows. All three CFBD datasets are now AVAILABLE with real data, using the same
`Authorization: Bearer <key>` header `cfbd.py` already had in place per D3's original design
intent (no other code change needed).

**FantasyPros: key present and transmitted, but rejected by FantasyPros itself — not resolved.**
`sources status` still reports `ERROR` (`403 Forbidden`) for both `consensus_rankings` and
`projections`. To rule out a proxy-level block (the D3/D31-era failure mode, which
`fantasypros.py` only catches as `httpx.ProxyError` → `SourceBlockedError`), called the real
endpoint directly with `curl -D -` to inspect raw headers: the CONNECT tunnel succeeds
(`HTTP/1.1 200 Connection Established`), and the `403` comes back from FantasyPros's own AWS
infrastructure (`x-amzn-errortype: ForbiddenException`, `via: ... cloudfront.net`, body
`{"message":"Forbidden"}`) — i.e. this is a real app-level auth rejection, not an egress block,
and not an env-var-pickup problem (the key is confirmed present and is being sent as the
`x-api-key` header exactly as `fantasypros.py` sends it). The key itself was sanity-checked for
whitespace/quoting corruption (none found; 40 chars, no leading/trailing whitespace, no quote
characters) and is not a network-layer problem, since CFBD's key against a different provider
went through cleanly with the same session/proxy in the same run.

**What's notable, and deliberately not guessed past:** the response body is byte-for-byte
identical to D31's unauthenticated probe of the same endpoint (`{"message":"Forbidden"}`, same
error type). An unauthenticated call and an authenticated-but-rejected call producing the exact
same response is consistent with several different root causes this repo cannot distinguish from
the outside — an invalid or expired key, a FantasyPros plan/tier that doesn't include API access,
a wrong auth mechanism for this specific v2 endpoint, or (given D35's leak/rotation history)
the possibility that the value now configured is not actually a freshly-rotated key. Per this
project's rule against guessing past what's actually verified, none of these is asserted; the
user was told directly which of the two keys needs their attention and why, rather than the
adapter code being changed speculatively (e.g. trying a different header format) without evidence
that would fix it.

**What this changes:** `docs/DATA_SOURCES.md` updated — CFBD moved to the AVAILABLE section;
FantasyPros's credential-gated entry updated to describe the new, more specific failure mode.
`docs/TRACEABILITY.md`'s CFBD row updated to ✅ MET; FantasyPros's stays ⚠️ but with the updated
reason. `docs/PROJECT_STATE.md`'s "pending confirmation from a fresh session" note resolved for
CFBD, updated (not resolved) for FantasyPros.

**What this doesn't change:** DynastyProcess/cfbfastR-data substitutes stay wired in as the
operating path for FantasyPros's ECR signal (CFBD's college-production role can now also be
served directly, but cfbfastR-data is left in place rather than removed — no product decision was
made to prefer one over the other for existing pipeline code, and switching is out of scope for a
credentials-verification pass). No code depends on live CFBD or FantasyPros calls yet; wiring
either into the pipeline for something new is, per D31, a deliberate product decision left for
direction rather than assumed here.

## D37 — D36's FantasyPros `403 Forbidden` was a wrong adapter base URL, not a bad/unrotated key — fixed, confirmed AVAILABLE with real data

D36 confirmed the key was present, correctly transmitted, and that the network layer was open
(not a proxy/policy block), but deliberately stopped short of asserting a root cause for the
`403 Forbidden` — it named several plausible explanations (invalid/expired key, wrong plan/tier,
wrong auth mechanism, or, given D35's leak history, the key not actually having been rotated) and
asked the user rather than guessing. The user confirmed the key in the environment was already
the correctly-rotated one, which ruled out the D35-rotation explanation and narrowed the search.

That narrowing made it worth checking the remaining explanations against FantasyPros's own
documentation rather than continuing to treat this as unresolvable from inside the repo. A web
search turned up FantasyPros's public API reference (`api.fantasypros.com/public/v2/docs`), which
states the real base path is `https://api.fantasypros.com/public/v2/json` — `sources/fantasypros.py`
had `https://api.fantasypros.com/v2/json` (missing `/public`). Verified directly with `curl`
before touching code: the wrong path returns `403`/`ForbiddenException` from FantasyPros's real
AWS API Gateway (byte-identical to D31's unauthenticated probe, which is what made it look like a
credentials problem — a wrong-resource rejection and a bad-key rejection look the same from the
outside), while the corrected `/public/v2/json` path returns real `200` data for both
`consensus_rankings` (real player rankings, e.g. Ja'Marr Chase at WR1) and `projections` with the
exact same key, unchanged.

**Fix:** corrected `_BASE` in `sources/fantasypros.py`; no key rotation, header change, or other
code change was needed. Re-ran `alpha-squad sources status`: both `fantasypros` datasets now
report AVAILABLE with real data (10 rows/25 columns and 10 rows/7 columns for the default
WR/ros health-check params). Also updated the module's docstring, which still described the old
D3-era "blocked by proxy policy" state.

**Regression coverage added:** `tests/integration/test_sources_live.py` previously had no
`network`-marked test proving FantasyPros or CFBD are reachable with a real key — only a
"without key" test existed for FantasyPros, and no live test at all for CFBD. Added
`test_fantasypros_with_key_is_really_reachable` and `test_cfbd_with_key_is_really_reachable`
(both skip rather than fail when no key is configured, since a paid/free key isn't guaranteed in
every environment) so a regression in either adapter's URL, auth header, or the provider's own
API surface gets caught by `make test-network` rather than silently reappearing. `make test`
(222 passed) and `make lint` both stay clean.

**What this changes:** `docs/DATA_SOURCES.md` — FantasyPros moved from "network-reachable but
credential-gated" into the AVAILABLE section, describing the real root cause instead of the
credentials-vs-policy framing D36 used while the cause was still unknown. `docs/TRACEABILITY.md`'s
FantasyPros row moves from ⚠️ to ✅ MET. `docs/PROJECT_STATE.md`'s FantasyPros note updated to
match — no longer "needs the user to check the key," since the key was never the problem.

**What this doesn't change:** the same as D36 — DynastyProcess/cfbfastR-data substitutes stay
wired in as the operating path in existing pipeline code; nothing currently calls the live
FantasyPros or CFBD adapters outside health checks, and wiring either in for something new is a
deliberate product decision left for direction, not assumed here. The broader lesson worth
keeping: a `403` from a real API Gateway response and a `403` from a proxy/policy block can look
identical from a single status code, and even a byte-identical error body across an unauthenticated
and an authenticated-but-wrong-resource request doesn't by itself distinguish "bad key" from
"bad URL" — checking the provider's own documentation before concluding either resolved this
faster than continuing to guess between credential explanations.

## D38 — Now-live FantasyPros/CFBD actually wired in: a new live FantasyPros market series, and a real (non-fuzzy) identity bridge that resolves D20's college-production gap

D37 left both keys confirmed live but unused by any pipeline code beyond health checks —
"wiring either in for something new is a deliberate product decision... left for direction, not
assumed." Asked directly whether that wiring should now happen. Two separate decisions, each
checked against real data before writing any code rather than assumed from the source becoming
reachable:

**FantasyPros: start a live snapshot series (user's chosen direction, over a cross-check-only or
leave-unused alternative).** `market/consensus.py::build_market_snapshot` reads DynastyProcess's
`fp_ecr_history` — a real *historical* time series that backtesting/EDGE (D16/D21) depend on for
leakage-safe as-of joins. The live FantasyPros API has no lookback of its own — every call
returns only *today's* rankings — so it can never be a drop-in replacement for that series; it
can only be a new, separately-provenanced series accumulated forward from whenever it first
runs, the same shape of problem `evidence/sleeper_trending.py` (D32) already solved for a
different live-only source. Implementation: `market_snapshot` gained a `source` column
(default `'dynastyprocess'`, PK extended to include it) so a live capture can never collide with
or silently overwrite a DynastyProcess-sourced row for the same player/date/ecr_type — verified
directly (inserted both for the identical key, both rows persisted, no clobber, INSERT is
idempotent on re-run). `build_live_fantasypros_snapshot` fetches `consensus_rankings`
(`position=ALL`, real data reveals `type=ROS` is silently ignored on this key's free tier — see
below) and inserts as `source='fantasypros_live'`.

**Real finding, not assumed:** requested `type=ROS` per FantasyPros's own documented enum
(`SPORTRankingTypes` — confirmed valid, case-sensitive uppercase, via the real OpenAPI spec at
`api.fantasypros.com/public/v2/docs/fantasypros_v2_public.yml`, D37's same doc). The live
response's own `type`/`ranking_type_name` fields always echo back `"Draft"`/`"draft"` regardless
of what's requested — checked with and without a `scoring` param, consistent both times. Rather
than mislabel this as ROS data it doesn't actually contain, tagged it `ecr_type='draft_overall'`
— an honest label for what's genuinely being captured (this key's free/public tier's Draft-type
overall consensus), not a guess at what a higher tier might unlock. Also fixed in passing:
`default_health_params`'s `type: "ros"` (lowercase) was being silently ignored by the real API
the same way — the real enum values are uppercase; changed to `"ROS"` even though it doesn't
change what tier serves, so the health check at least sends what it means to.

**CFBD: yes, build the rookie feature (user's explicit direction).** D20 had already ruled out
cfbfastR-data for college production — not for lack of a source, but because its numeric
ESPN-style player IDs have no verified bridge to this project's nflverse-derived identity graph,
and building one via name+school+season fuzzy matching was judged not worth the engineering cost
given draft capital's own strength as a proxy. Before writing any rookie-modeling code, checked
whether switching from cfbfastR-data to direct CFBD access changes that verdict — it doesn't on
its own: cfbfastR-data is itself built by mirroring CFBD's own API, so its numeric IDs are the
same underlying ID space D20 already found unbridged, not a fresh namespace.

**What actually resolves it:** CFBD's `/draft/picks` endpoint returns both `collegeAthleteId` and
`nflAthleteId` per real drafted player. Checked `collegeAthleteId` against DynastyProcess's
`espn_id` for 4 real players (Caleb Williams, Jayden Daniels, Drake Maye, Marvin Harrison Jr.) —
exact match, 4/4, no fuzzy logic involved: CFBD's numeric athlete ID *is* ESPN's athlete ID.
`espn_id` was present in DynastyProcess's own crosswalk CSV but omitted from
`identity/crosswalk.py`'s `DYNASTYPROCESS_ID_COLUMNS` — added it, one line, reusing the existing
`insert_id_mappings` machinery unchanged. This is a real, verified, non-fuzzy identity bridge,
not the "materially larger undertaking" D20 correctly avoided; it supersedes D20's verdict for
CFBD specifically without contradicting D20's original reasoning about cfbfastR-data's own ID space.

**CORRECTION (D39, 2026-08-23 — this paragraph as originally written was wrong).** The claim that
`espn_id` was "never loaded into `player_id_map`" was false, and was never verified against a
populated database (this container's DB was empty when D38 was written — `players` had 0 rows, so
no crosswalk had ever actually been built here). `identity/canonical.py:32` has always loaded
`espn_id` from nflverse's own `players` table. The first real `identity build` shows
**16,771 `espn_id` mappings: 16,761 from `nflverse_players`, and only 10 net-new from the
DynastyProcess column D38 added** (plus 6 cross-source conflicts correctly quarantined). So the
espn_id↔CFBD bridge itself is real and holds at scale — that part of D38 stands and is what
resolves D20 — but **D38's own code change contributed ~0.06% of it**; the bridge was already
almost entirely present via nflverse. The DynastyProcess column is kept (it is harmless, adds 10
genuine mappings, and surfaces 6 real cross-source disagreements rather than silently picking a
winner), but D38 took credit for enabling a bridge that mostly already existed. The substantive
new work in D38 was the CFBD ingestion + the leakage-safe `rookie_features` join, not the identity
bridge.

**Necessary prerequisite bug found and fixed first:** `sources/cfbd.py` and `sources/fantasypros.py`
wrote every same-day snapshot to a `local_path` keyed only by dataset + captured-at date, ignoring
query params — unlike `sources/file_release.py`'s existing `param_suffix` pattern. Fetching CFBD
`player_usage` for multiple seasons (exactly what college-usage ingestion needs) would have
silently overwritten each season's file on disk while `snapshot_registry` still recorded distinct
rows pointing at the now-wrong content — a real provenance bug, caught before it could produce a
single row of fabricated-by-omission data. Fixed both adapters to include a param suffix in the
filename, matching `file_release.py`; added a regression test proving two same-day fetches with
different params no longer collide.

**Implementation:** `college_usage` (new table: player_id, season, usage_overall/pass/rush,
source_snapshot_id) is built by `features/college_production.py::build_college_usage`, looping
`CfbdSource.fetch("player_usage", year=...)` over every season a rookie in `players` actually
needs (`seasons_needed_for_rookies`: `DISTINCT rookie_season - 1` for skill-position rookies),
joined via `player_id_map WHERE id_type='espn_id'`. `features/rookie.py::build_rookie_features`
LEFT JOINs `college_usage` on `(player_id, season = rookie_season - 1)` — the player's *final
college season only*, never their own NFL season, the same leakage rule
`landing_team_prior_pass_rate` already follows (verified with a regression test: a
`college_usage` row that shares the rookie's *NFL* season number, not their college one, must
not join in). `models/rookie/features.py`'s `FEATURES` gained `college_usage_overall/pass/rush`;
missing values impute to 0.0, same convention already used for missing combine measurables.
`FEATURE_VERSION` bumped `rookie_features_v1` -> `rookie_features_v2` so a future training run is
correctly distinguished from anything trained on the old 12-feature set.

**Verified against real data throughout, not assumed:** every new function was smoke-tested
against the real live APIs before any unit test was written — `build_live_fantasypros_snapshot`
correctly resolved Ja'Marr Chase's real WR1 overall rank via the real join; `build_college_usage`
pulled Caleb Williams's real 2023 USC usage share (overall 0.624, pass 0.915, rush 0.222) via the
real espn_id bridge; `build_rookie_features` correctly joined that through into `rookie_features`
end-to-end. Offline regression coverage added afterward
(`tests/unit/test_market_live_fantasypros.py`, `tests/unit/test_college_production.py`, new cases
in `tests/unit/test_rookie_models.py`, plus the path-collision test in
`tests/contracts/test_source_adapters.py`) mocks httpx with these exact real response shapes.
`make test` (237 passed) and `make lint` both clean.

**What this doesn't do:** no rookie model was retrained or re-evaluated against the new v2
feature set — that requires a full pipeline run (`sources ingest` -> `identity build` ->
`features build-college-usage` -> `features build` -> `models rookie train`) against real
multi-season data, a heavier, separate operational step from wiring the feature in correctly and
proving it joins leakage-safely. Until that run happens, `rookie_features_v2`'s three new columns
exist, are correctly populated, and are in `FEATURES`, but no trained model has actually used
them yet — this is deliberately not claimed as "the rookie model got better," only as "the
missing signal is now real, correctly joined, and ready to train on." Also unchanged: the
DynastyProcess/cfbfastR-data substitutes stay wired in as the operating path in existing
pipeline code (no product decision was made to remove either), and per-expert FantasyPros
weighting stays LIMITED regardless (D4) — this tier's consensus-only data doesn't touch that gap.

## D39 — First real end-to-end pipeline run: college production measured and NOT adopted; three real bugs found, including a schema-migration gap that made D38 broken-on-upgrade

D38 wired CFBD college production into `rookie_features` and bumped the feature set to v2, but
explicitly did not claim the model improved — no model had been trained on it. This entry is
that missing measurement, plus what running the real pipeline for the first time exposed. The
database in this container was empty (`players` = 0 rows) before this run, so nothing in D38 had
ever executed against real data end to end.

**Pipeline actually run** (2012–2025): `sources ingest` (155 OK / 20 NOT_FOUND, all expected —
2026 preseason and pre-2022 `ftn_charting`) → `identity build` (25,050 players) →
`features build-college-usage` → `features build` (241,208 player-weeks, 26,816 player-seasons,
1,360 rookie-seasons) → `train rookie --ablation`.

### The measurement

A naive "train v2 and look at the numbers" cannot answer this: `evaluation_results` and
`classification_results` are keyed on (model_name, season|cohort, position), so a second training
run silently overwrites the first and leaves no baseline. So `run_rookie_models` gained optional
`features`/`feature_version`/`model_suffix` parameters (defaulting to production, so no existing
caller changes), `models/rookie/ablation.py` pairs the two arms fold by fold, and
`train rookie --ablation` runs both over identical folds with identical hyperparameters and seed.

**Decision rule, fixed before any numbers were seen:** the breakout classifier is the
decision-relevant output, so Brier governs; regression Spearman is secondary; adopt the college
features only if the classifier improves.

**Result — primary (draft classes 2019–2025, 28 paired folds each):**

| metric | baseline | +college | delta | better |
|---|---|---|---|---|
| regression MAE (lower better) | 37.5379 | 37.5968 | +0.0589 | baseline |
| regression Spearman (higher better) | 0.6182 | 0.6179 | −0.0003 | baseline |
| breakout Brier (lower better) | 0.0678 | 0.0708 | +0.0030 | baseline |
| breakout accuracy (higher better) | 0.8994 | 0.9005 | +0.0010 | +college |

**Robustness check.** Coverage is heavily skewed — CFBD's `player/usage` returns nothing before
2013, and real coverage of `rookie_features` runs 0% for classes 2012–2015, 5% (2016), 26%
(2017), 56% (2018), then 83–97% for 2019–2025. Since `models/rookie/data.py` imputes a missing
college value to 0.0, a plausible alternative explanation for the null result was a train/serve
mismatch: models trained mostly on zero-imputed classes, then asked to predict classes where the
feature is genuinely present. So the ablation was re-run restricted to classes where *both*
training and target data are ≥83% covered (targets 2022–2025, training from 2019; 16 paired
folds). That made it **worse, not better** — baseline wins all four metrics there
(MAE +1.0585, Spearman −0.0016, Brier +0.0032, accuracy −0.0099). The coverage cliff is not the
explanation; the signal simply is not there.

**Decision: KEEP BASELINE.** `FEATURES` reverts to the 12-feature D20 set and `FEATURE_VERSION`
back to `rookie_features_v1` — claiming v2 would misdescribe every model registered and every
prediction written. What is deliberately *kept*: the CFBD ingestion, the `college_usage` table,
the `rookie_features` columns, the espn_id bridge, `FEATURES_WITH_COLLEGE`, and the whole
ablation harness. The data is real, correctly joined, and leakage-safe; the experiment is now
one command to re-run (`train rookie --ablation`) if CFBD backfills older seasons or someone
engineers a college feature with more signal than raw usage share. Reports:
`reports/rookie_college_production_ablation.md` and `..._highcov.md`.

An honest reading of D38 in hindsight: it was a well-built pipeline for a feature that does not
earn its place. That is a normal experimental outcome, and the value delivered is the
now-reproducible ability to ask the question, not a model improvement.

### Three real bugs found by running it for real

1. **`init_db` had no migration path — D38 was broken on upgrade.** Every DDL statement is
   `CREATE TABLE IF NOT EXISTS`, which is idempotent for new tables but silently ignores a
   *column* added to an existing one. D38 added `rookie_features.college_usage_*` and
   `market_snapshot.source` (and widened market_snapshot's PRIMARY KEY) and was verified only
   against fresh in-memory test databases — so the entire suite passed while any pre-existing
   database would hard-crash: `features build` died with
   `BinderException: Referenced update column college_usage_overall not found in table`, and
   `market capture-live-fantasypros` would have failed the same way. Fixed with a real migration
   path (`ADD_COLUMN_MIGRATIONS` + a guarded `market_snapshot` rebuild, since DuckDB cannot ALTER
   a primary key) applied by `init_db`, and `tests/unit/test_schema_migrations.py` which builds
   the *old* schema first — the one thing no other test in this suite does.

2. **The ablation's own fold-pairing was wrong, and produced a plausible-looking false result.**
   `run_rookie_models` trains one model per position, but `evaluate_and_record` reports each
   one's headline row at `position='ALL'`. Keying folds on (class, position) therefore collapsed
   all four position models onto one key and compared the candidate's QB model against the
   baseline's TE model. The first run reported a **+13.69 MAE regression** — caught only because
   that is implausible next to a −0.0003 Spearman delta, not because anything failed. Real
   per-model deltas were ~0.06. Fixed by including the (suffix-stripped) model name in the fold
   key; `tests/unit/test_rookie_ablation.py` asserts identical arms produce exactly zero delta,
   which is what fails under the collapsing key.

3. **`load_rookie_class_data` hardcoded `FEATURES` in its SELECT**, so once production reverted
   to the 12-feature set the ablation's candidate arm got a DataFrame missing the columns it
   asked for and died on a pandas `KeyError` at fit time. Now takes a `features` parameter.

Two smaller ones, also from real execution: `_prediction_id` did not include `feature_version`,
so two arms predicting the same player/class collided on `rookie_predictions`' primary key (the
UNIQUE-targeted ON CONFLICT clause does not catch that); and `_register_model`'s
`ON CONFLICT DO UPDATE` omitted `feature_version`, leaving a stale value on re-training.

### D38 correction, and a pipeline-ordering trap

`seasons_needed_for_rookies` had no lower bound, so it derived college seasons from the full
nflverse history and issued ~40 real CFBD requests back to **1973**, every one returning an empty
list (verified: 1973/1990/2004/2010 → `[]`, 2013 → 2991 rows). Floored at
`CFBD_USAGE_FIRST_SEASON = 2013`. Separately, D38's claim that `espn_id` was "never loaded into
`player_id_map`" was false and is corrected in place above — `identity/canonical.py:32` always
loaded it from nflverse; of 16,771 espn_id mappings, 16,761 come from nflverse and only 10 from
the column D38 added.

**A fourth bug, found by running the actual app.** With the pipeline populated, the FastAPI
backend and the React SPA were launched and driven in a real browser (all six views, plus a live
draft recommendation and a rookie-comps drill-down). `GET /rookies` returned **every rookie once
per trained model version** — `rookie_predictions` is legitimately keyed on
(player, draft_class, model_version), and the ablation made that several versions, so Ashton
Jeanty appeared three times with three different numbers. It reads as duplicate players, not as
alternative models. The endpoint now filters to the production `FEATURE_VERSION` by default, with
an optional `model_version` query param to inspect an arm. No test covered this and none would
have: it only appears once more than one arm has been trained against the same database.

Finally, D38 left a trap: `features build-college-usage` must run **between** `identity build`
and `features build`, because `features build` is what joins `college_usage` into
`rookie_features`. Running it after instead leaves the columns NULL, which `data.py` imputes to
0.0 — i.e. the model trains on zeroed college features with no warning. There was no Makefile
target and no README step for it, so `make ingest && make identity && make features && make train`
did exactly that. Both now fixed.

## D40 — The app was projecting an already-played rookie class; three chained defects kept the incoming 2026 class unprojectable

Reported by the user against the running app in August 2026: the Rookies view showed the 2025
class. That is a backtest, not a forecast — the 2025 season has been played. The incoming class
(Fernando Mendoza, Ty Simpson, KC Concepcion et al.) was absent entirely. Three independent
defects, each of which alone was sufficient to cause it:

**1. nflverse's `players` file lags the draft, and `draft_picks` changed shape.** All 694
`rookie_season=2026` rows in nflverse `players` have a NULL `draft_year`, while `draft_picks`
already carries the full 257-pick 2026 draft. Draft capital is the single strongest rookie
feature (D20), so without it the class cannot be projected meaningfully at all. Worse, the
obvious join fails: `draft_picks.gsis_id` holds real gsis ids for 2022–2025 (262/259/257/257 rows,
all `00-%`) but for 2026 holds **230 esb-style ids and zero real gsis ids** — real gsis ids are
evidently assigned later. Fixed by COALESCEing draft capital from `draft_picks` inside
`build_players_spine`, joining `gsis_id` with an `esb_id` fallback. Done inside the spine build
rather than as a follow-up UPDATE because DuckDB implements UPDATE as delete+insert and refuses
it on a table other tables hold foreign keys into, which `players` is (hit this for real).

**2. The spine upsert could never refresh draft capital.** `ON CONFLICT (player_id) DO UPDATE`
listed only display_name/position/position_group/last_season/status. A player who first enters
`players` before their draft data is published — i.e. every incoming rookie — keeps NULL capital
forever, no matter how many times identity is rebuilt. Now COALESCE-updates draft_round/pick/team,
draft_year and rookie_season, so a later snapshot can fill a gap but never erase a known value.
After the fix, 74 of the 234 2026 skill players carry real capital (Mendoza R1P1 LVR, Simpson
R1P13 LAR, Concepcion R1P24 CLE); the remaining ~160 are genuine UDFAs and take the existing
`UNDRAFTED_*_FALLBACK` path.

**3. `rookie_features` structurally cannot hold an unplayed class.** It INNER JOINs
`player_season_stats` on the rookie's *own* season and declares `rookie_year_ppr_points` /
`breakout_top24` NOT NULL — correctly, because it is the labeled training set. So even with
capital fixed, the 2026 class had nowhere to live. Added `rookie_projection_features` (same
feature columns, no outcome) and `project_rookie_class()`, which trains on every labeled class
before the target and writes `rookie_predictions` **without** any evaluation rows — there is no
outcome to score against, and publishing a metric for an unplayed season would fabricate one.

Kept as a separate table rather than relaxing `rookie_features` to nullable outcomes, so an
unlabeled row can never be silently picked up as training data. The feature SQL itself is shared
verbatim between the two builders (`_FEATURE_CTES`/`_FEATURE_SELECT`/`_FEATURE_JOINS`) and the
imputation is shared between the two loaders (`_impute`): the labeled and unlabeled paths MUST
compute features identically, since one trains the model and the other is what the model is asked
to score, and divergence there would be silent and severe.

**Result** (`alpha-squad train rookie-project --draft-class 2026`, trained on classes 2000–2025,
234 players): Jeremiyah Love (RB, R1P3) 233.3 pts / 88% breakout; Carnell Tate (WR, R1P4) 202.8 /
48%; Fernando Mendoza (QB, R1P1) 196.3 / 86%; Ty Simpson (QB, R1P13) 177.4 / 57%; KC Concepcion
(WR, R1P24) 139.9 / 15%.

**The stale default itself.** The UI hardcoded `useState(2025)`, which is how an already-played
class was on screen. Hardcoding 2026 just re-breaks next August, so `GET /rookies/classes` now
returns the classes that actually have predictions (newest first) and the view defaults to the
newest. Three sibling views (Rankings, EDGE, League) still hardcode a 2025 season default; they
are left as-is deliberately because the data behind them genuinely stops at 2025 — changing the
default without generating 2026 rankings/EDGE would show an empty view, which is worse. That is
recorded here as a known limitation rather than silently half-fixed.

**A process note.** `npx tsc --noEmit` at the repo root reported success on frontend code that
was actually broken (`get is not defined` — I had called a helper that does not exist). The root
`tsconfig.json` is a project-references stub and type-checks nothing; the real check is
`tsc -p tsconfig.app.json`. The error surfaced only when the page was driven in a real browser.
Worth knowing before trusting a green typecheck here.

## D41 — Reviewable EDGE backtest artifact (`edge backtest`, `reports/edge_backtest.md`)

`docs/CURRENT_STATE_AUDIT.md`'s P1-2 gap: `edge validate`'s per-(season, action) backtest logic
was real (`evaluate_historical_edge`) but had never been re-run against the current live-sourced
market data in this deployment, so no report existed to review. Confirmed `reports/` is
gitignored by design (CLAUDE.md: reproducible from the pipeline, never committed) — the actual
gap was that the report had never been generated, not that it existed but wasn't committed.

Added `evaluate_historical_edge_detailed`/`write_edge_backtest_report` (`market/edge.py`) and
`alpha-squad edge backtest` (`cli.py`). Reuses `evaluate_historical_edge`'s exact walk-forward
market-implied-points methodology (same `_market_implied_points_curve`, trained only on
strictly-prior seasons) rather than reimplementing a different backtest — just slices the same
underlying (actual, market-implied) pairs by position and by rank-edge/points-edge/confidence
magnitude bucket, and writes methodology/limitations/failure-modes sections alongside the
tables. Unit-tested (`tests/unit/test_edge.py::TestEvaluateHistoricalEdgeDetailed`, 4 new cases).

**Real result, run 2026-08-24 against 2022–2025 (1543 signals, 659 players, `ecr_type=rsf`):**
BUY beat market-implied points in **all 4** scored seasons (+27.2 / +19.2 / +18.8 / +4.7 pts —
positive throughout, though declining in magnitude, worth watching but not treated as a problem
here since the direction never flipped). SELL was genuinely mixed: correctly negative
(underperformed as expected) in 2022–2023, roughly neutral in 2024, and wrong-direction in 2025.
Reported as-is, not smoothed over, per CLAUDE.md's no-hidden-failure rule; the model was not
re-tuned against this result. `docs/TRACEABILITY.md`'s Market/EDGE row updated to point at both
reports and summarize the current numbers instead of a stale prior claim ("3 of 4 seasons").

## D42 — P0 security follow-up: no history rewrite performed (already decided in D35); added a durable CI guardrail instead

`docs/CURRENT_STATE_AUDIT.md`'s P0 flagged the D35 leaked-key exposure as still live in Git
history and asked for either a history rewrite with explicit user sign-off, or an explicit
documented decision not to. Re-reading D35 itself: **that decision was already made** --
the user was offered a full `git filter-repo` + force-push history purge at the time and
**explicitly declined it**, on the reasoning that it is strictly more invasive than the file fix
(rewrites shared history, orphans every existing clone) and still would not undo the actual
exposure (only provider-side key rotation does that, which is outside what this repo can verify
or perform). The user was told directly, more than once, to rotate both keys at FantasyPros and
CFBD. Nothing in this session changes that picture or reopens that decision -- there is no new
information here that would justify re-litigating a decision the user already made, and this
autonomous session does not have standing to perform a destructive, irreversible, shared-history
rewrite on its own initiative regardless. **No history rewrite was performed.**

What *is* new and safe: a durable, non-destructive guardrail against a repeat. Added
`scripts/check_no_secrets.py` (`make check-secrets`, now part of `make lint`, so CI enforces it
on every push/PR): scans every git-tracked `*.env.example` file for a secret-shaped key
(`*_KEY`/`*_SECRET`/`*_TOKEN`/`*_PASSWORD`/`*_CREDENTIAL`) with a non-empty value and fails the
build if it finds one -- verified against a synthetic fixture that reproduces D35's exact
pattern (real key committed to `.env.example`) and confirmed it catches it (exit 1). Unit-tested
(`tests/unit/test_check_no_secrets.py`, 5 cases; one real bug in the first draft -- an anchored
`.match()` where a `.search()`-on-suffix was needed -- was caught by these tests before commit,
not after). Also fixed `.env.example`'s stale D33/D34 cross-reference (should have been D35) and
its stale "Sleeper/FantasyPros/CFBD blocked by egress policy" note, both superseded by D36/D37.

This closes the "was a decision even made" ambiguity the audit raised (yes, in D35) and adds a
guardrail so the same failure mode can't recur silently. It does not and cannot verify whether
the user has actually rotated the two leaked keys at their respective providers -- that remains
outside what this repo can check, exactly as D35 already stated.

## D43 — Model artifact persistence: the missing inference-only serving path (P1-3)

`docs/CURRENT_STATE_AUDIT.md`'s biggest architectural finding: no model was ever saved to disk
anywhere in this codebase (`grep` for `save_model`/`joblib.dump`/`pickle.dump` in `src/` found
nothing) -- every prediction the API served, including `/rankings` (backed by
`uncertainty_predictions`) and `/rookies` (backed by `rookie_predictions`), existed only because
some CLI run had trained a model, scored it, and thrown the fitted object away in the same
process. There was no way to refresh even one player's prediction without re-running the entire
multi-season/multi-decade walk-forward training loop.

Added `src/alpha_squad/models/persistence.py`: generic save/load for CatBoost regressors and
classifiers (native `.cbm` format under `models/{model_version}/{model_name}_{position}.cbm`,
gitignored like everything else under `models/`), plus a `model_registry` upsert carrying the
artifact path and (for models whose serving story needs more than the point prediction, like
uncertainty's conformal quantiles) the calibration residuals as JSON. New nullable columns
`model_registry.artifact_path`/`calibration_residuals_json` via the standard `ADD_COLUMN_MIGRATIONS`
path -- existing rows are unaffected.

Wired into the two actual serving paths, both opt-in via a `persist` flag (default off for
`run_uncertainty`'s own walk-forward *evaluation* callers -- no reason to write dozens of
intermediate historical artifacts to disk just to compute backtest metrics -- default **on** for
the CLI's real production commands):
- `models/uncertainty/run.py::run_uncertainty(persist=True)` + new
  `score_with_persisted_model(con, position, season, feature_rows)` -- loads the saved model and
  calibration residuals, scores new feature rows, reconstructs the exact same p10-p90/top-12/24
  output with no `.fit()` call.
- `models/rookie/train.py::project_rookie_class(persist=True)` + new
  `score_rookie_projection_with_persisted_model(con, position, draft_class, feature_rows)` --
  same idea for the forward (unplayed-class) rookie projection; also fixed a pre-existing gap
  where the classifier was never registered in `model_registry` at all (only the regressor was).

CLI: `train uncertainty`/`train rookie-project` both default to `--persist` now (real usage
should always leave a servable artifact behind); two new commands,
`alpha-squad models rescore-uncertainty` and `alpha-squad models rescore-rookie-projection`,
demonstrate the actual inference-only path end to end.

**Verified against the real database, not just synthetic fixtures:** ran
`alpha-squad train uncertainty --season-start 2025 --season-end 2025 --persist` (453 predictions,
real coverage numbers written to `reports/calibration_report.md`), confirmed a real `.cbm` file
+ calibration residuals landed in `model_registry`, then ran
`alpha-squad models rescore-uncertainty --position WR --season 2025 --player-ids <real player>`
and got back the same point/p10/p90 the training run had stored, with no retraining. Same for
rookies: ran `alpha-squad train rookie-project --draft-class 2026 --persist` (234 predictions,
real 2026 class), then `alpha-squad models rescore-rookie-projection --position QB --draft-class
2026 --player-ids <Fernando Mendoza's player_id>` and got back exactly 196.3 pts / 86% breakout
-- the same numbers the training run produced, reproduced purely from the loaded artifact.

Regression-tested (`tests/unit/test_uncertainty_run.py::TestPersistedModelInference`,
`tests/unit/test_rookie_models.py::TestRookieProjectionPersistedInference`, 6 new cases): proves
byte-exact reproduction of training-time predictions from the persisted artifact, and that
scoring without a prior persist raises `FileNotFoundError` rather than failing silently or
fabricating output.

Scope decision: established-player season-level/weekly models (`models/established/`) were left
unpersisted. Unlike uncertainty (`/rankings`) and the rookie projection (`/rookies`), nothing in
the API currently serves established-model output live -- it feeds `evaluation_results` for
reporting/comparison only -- so persisting it would add a servable artifact nothing reads yet.
Flagged in `docs/IMPLEMENTATION_GAP_ANALYSIS.md` as a follow-up if/when `/rankings` is extended
to read established-model output directly rather than only the uncertainty model's.

## D44 — Wired waiver, trade, and roster-need into the UI (`docs/CURRENT_STATE_AUDIT.md`'s largest Application/interface gap)

The audit found real, tested, live-verified league-decision logic for waiver/FAAB
(`league/waiver.py::recommend_waiver_pickup`), dynasty trade (`league/trade.py::recommend_dynasty_trade`),
and roster need (`league/roster.py::roster_need`), all exposed via FastAPI
(`api/routers/league.py`) and already covered by `api.postWaiver`/`api.postTrade`/`api.getRosterNeed`
in `web/src/api.ts` — but with no UI view calling any of the three. Only the draft form in
`LeagueView.tsx` was reachable. Frontend-only change, per the assignment's hard constraint; nothing
under `src/alpha_squad/` was touched.

**Added `web/src/components/WaiverView.tsx`** (new): league selector (same
`localStorage`/`listLeagues` pattern as `LeagueView.tsx`, sharing the same
`alpha-squad:last-league-id` key so the selected league persists across tabs), season/week/player-id/
roster-positions inputs, calls `api.postWaiver`. The result card labels `expected_value` as
"Recommended FAAB bid" and `confidence` as "Meaningful-role (top-24) probability" rather than generic
names, since that's what `post_waiver` actually maps them from (`league.py:142-156`) — a generic
label would have misrepresented what the number means.

**Added `web/src/components/TradeView.tsx`** (new): same conventions, calls `api.postTrade`. Read
`league/trade.py::recommend_dynasty_trade`'s real signature first — it evaluates one player's
age-adjusted dynasty value/EDGE action, not a multi-player trade package — so the form takes a single
`player_id`, not two "sides" of a trade; the panel's copy says so explicitly rather than implying a
capability the backend doesn't have. Noticed but did **not** fix (frontend-only constraint): 
`recommend_dynasty_trade`'s `TradeRecommendation.action` (BUY/HOLD/SELL/WATCH) is computed but never
copied into `DecisionResponse` by `post_trade` (`league.py:159-184`) — only `player_id`,
`age_adjusted_value`, and `reasons` cross the API boundary. The action is usually still recoverable
from the `reasons` text (`market/edge.py`'s gating function prefixes the winning branch's reason with
`"BUY:"`/`"SELL:"`), but a client that wanted the clean enum value cannot get one today. Flagging
this as a real, minor backend gap rather than fixing it or fabricating an action badge client-side
from parsed text.

**`LeagueView.tsx`**: added a "Roster need" section directly under the league-context card, calling
`api.getRosterNeed(leagueId, rosterPositions)` on a new "Check roster need" button. Reused the
existing `rosterPositions` input (moved it out of the draft-recommendation controls into this shared
section, since both the roster-need call and the draft call already read the same state variable) —
per the assignment, deliberately not duplicated. Renders `need` as a small position/score table.
Confirmed the draft recommendation still works unchanged after the input's relocation (same
`recommend_draft_pick` call, same state variable, just moved which JSX block renders the `<input>`).

**`App.tsx`**: registered "Waiver" and "Trade" tabs in `TABS`, same pattern as the existing six.

**Verification.** `npm run build` (`tsc -b && vite build`, the real typecheck per the prior session's
process note above) and `npm run lint` (oxlint) both clean — zero errors; lint's only output is four
pre-existing `react/set-state-in-effect` warnings in files this change didn't touch
(EdgeView/RankingsView/EvidenceView/RookiesView), at 0 exit code.

Then actually drove it: started the real backend (`make serve`, DuckDB copied from the already-
populated `data/alpha_squad.duckdb`, since this session ran in a fresh worktree with no prior
ingest) and the real frontend (`npm run dev`), and used Playwright (Chromium at
`/opt/pw-browsers`, installed into an ephemeral `uv run --with playwright` environment since neither
the Python nor the Node project had the `playwright` package itself, only the browser binary) against
the real `dilworth` Sleeper league:

- **Roster need** (`QB,RB,RB,WR,WR,TE`): rendered `QB 0.60, RB 0.60, WR 0.60, TE 0.60, K 1.00, DEF
  1.00` — real numbers from `roster_need`, not placeholders.
- **Draft** (season 2025, next pick #10): still recommends `asq_583ef9bed022a35b` with VORP/roster-
  fit/confidence/survival-probability reasons, unchanged after the input relocation.
- **Waiver** (season 2025, week 10, `asq_567a2eee58dd0e15` = Derrick Henry, roster `QB,RB`):
  recommended FAAB bid **$26.66**, meaningful-role probability **0.88**, with real reasons ("marginal
  value +65.5 pts above RB replacement (139.7)", "competing-bid likelihood 72%", "dynasty value (2QB)
  1237", etc.).
- **Trade** (season 2025, `asq_567a2eee58dd0e15`, ecr_type `rsf`): age-adjusted dynasty value **371**,
  with real reasons including "age 32.6 at RB: age-curve multiplier 0.30 (documented heuristic ...
  D25)" and "current dynasty value (2QB): 1237".

No console errors on any tab. All four decisions were also confirmed by direct `curl` against the
running API before and independent of the browser pass, so the browser result reflects the real
pipeline, not a UI-only mock.

`make test`: **259 passed, 42 deselected** — identical to `docs/CURRENT_STATE_AUDIT.md` §21's
directly-reproduced baseline (that section's number, not the differing "267" figure quoted second-hand
in this session's task brief, which does not match anything actually reproducible in this repo at
this commit). Confirms zero drift under `src/alpha_squad/`, as required — this was a frontend-only
change.

`docs/TRACEABILITY.md`'s Application/interface section and `docs/CURRENT_STATE_AUDIT.md` §5/§20
updated to cite this work and retire the PARTIAL status on the two rows this closed; §20 also notes
the one related gap this did *not* close (a simulation-based team-outlook view — no such endpoint
exists on either side of the API boundary today, a separate and larger piece of work).

## D45 — Future-draft-pick valuation in the trade engine (P2)

`docs/CURRENT_STATE_AUDIT.md`'s gap: `LeagueContext.future_picks` exists in the schema but
`trade.py::recommend_dynasty_trade` never read it -- no future-pick valuation logic existed
anywhere in `league/`. Checked `future_picks` itself first before wiring it in: it is a
free-form dict that is **always `{}`** in this deployment -- `sleeper_context.py` hardcodes
`future_picks={}` (no traded-picks Sleeper endpoint is called), and the static `target_league.yaml`
never populates it either. Wiring new logic to read an always-empty field would be dead code,
untestable against real data, and would silently do nothing for every real league this
deployment actually has. So pick assets are taken as **explicit caller-supplied input** instead
(the same pattern `draft.py`'s `available_player_ids` already uses instead of inferring
availability from context) -- real and testable today, and `future_picks` itself is left for a
follow-up once a real traded-picks data source exists to feed it.

Added `pick_value(round_, teams, pick_in_round, years_out)` (`league/trade.py`): a documented
heuristic, not fit from data -- there is no real fantasy-rookie-draft-slot outcome dataset in
this environment to fit one from (NFL draft position is a different thing from fantasy
startup/rookie-draft position, and nothing here provides the latter). Same treatment as the
pre-existing age curve (D25): disclosed as an assumption in every reason string, not presented
as validated. The value scale is anchored to real observed data, though: `dynasty_values.value_2qb`
runs 0-10232 (median 6) in this deployment, and a real 1st-overall rookie-class outcome has
reached 5767-8538 across the 2022-2025 classes -- `pick_value`'s round-1 base (2200) sits well
below that realized ceiling (which requires the pick to actually hit) and well above the median
outcome (which includes every bust), an explicit expected-value-under-uncertainty compromise.
Within-round slot and years-out both decay linearly/geometrically off that base.

Added `evaluate_trade_package(con, side_a, side_b, season, teams, ecr_type)`: sums real
age-adjusted dynasty value (unchanged `recommend_dynasty_trade` logic) for every player plus
real pick value for every pick asset on each side, and reports which side comes out ahead (or
"even" within a 10% threshold, so a razor-thin, not-actually-meaningful edge isn't reported as
a real recommendation). `POST /league/{id}/trade-package` and `alpha-squad league trade-package`
expose it. Verified against the real database: a 1.01 rookie pick + a real 0-value player
correctly valued at 2200 vs. a real elite dynasty asset (10232) -- favors the elite asset by a
wide, sensible margin, not a coin flip.

Regression-tested (`tests/unit/test_league.py::TestPickValue`/`TestEvaluateTradePackage`, 9 new
cases) and API-tested (`tests/unit/test_api.py`, 2 new cases) -- 284 offline tests passing
(up from 273).

## D46 — Evidence reaches served rankings: `GET /rankings/weekly` (closes P4 and P5 together)

`docs/CURRENT_STATE_AUDIT.md` flagged two separate-looking gaps that turned out to be the same
underlying one. Re-checked the architectural intent before assuming either resolution branch of
P4's instructions applied: PRODUCT_SPEC.md's Evidence section says "current information updates
the prior; it does not automatically override it," and ARCHITECTURE.md's pipeline diagram places
Evidence between {Projection ML, Rookie ML, Market} and Ensemble/EDGE, upstream of "Universal
Player Intelligence" -- i.e. evidence is supposed to reach what gets served, not just gate EDGE.
So this is the "implement it" branch, not the "document evidence-veto-only by design" branch.

Investigating why it didn't already: M9's real bounded (±15%) evidence adjustment
(`evidence/prior_update.py::apply_evidence_adjustment`/`run_prior_update`) operates on
`weekly_projection_snapshot` -- M5's **in-season weekly** established-ML projections -- writing
`projection_deltas`, never mutating the base. That's the right grain: evidence detectors only
ever produce in-season events (D23), so a weekly cadence is exactly where evidence timing
actually lines up, unlike the season-level preseason uncertainty model behind `/rankings`
(D23's real, structural timing mismatch there stands as documented). But `weekly_projection_snapshot`
had **never been populated in this deployment** -- `train established` (the weekly command,
distinct from `train established-season`) had never been run -- so `projection_deltas` had
nothing to adjust regardless of how good the evidence-adjustment code was, and no endpoint
served either table as a ranked view. This is the same root cause as P5's "in-season/ROS
intelligence" gap: not a missing modeling capability (the walk-forward-safe weekly pipeline
already existed and is real), but a missing production run plus a missing serving endpoint.

Fix: ran `alpha-squad train established --season-start 2025 --season-end 2025` against the real
database (6,037 real weekly predictions, 2025 weeks 1-19), then `alpha-squad evidence
update-projections --season 2025 --week 8` (291 real deltas, 95 materially adjusted --
e.g. Ja'Marr Chase +13.5% on a real target-share spike, Patrick Mahomes -13.5% on a real
snap-share drop, Mac Jones +13.5% on a real teammate-injury opportunity). Added
`GET /rankings/weekly` (`api/routers/rankings.py`) -- a direct LEFT JOIN of
`weekly_projection_snapshot`/`projection_deltas`, **ordered by the evidence-adjusted value**,
falling back to the unadjusted base for players with no evidence that week. Added the
`RankingsView.tsx` "Weekly (evidence-adjusted)" mode showing base/adjusted/change/reason per
player -- a user can now literally answer "why did this player's ranking change this week?"
from the UI, which PRODUCT_SPEC.md's Evidence section calls for directly.

Verified in a real browser (Playwright, not just the API): started the real backend + frontend,
navigated to the new mode, and confirmed a real row (Patrick Mahomes, -13.5%, real reason text)
rendered exactly as stored, no console errors.

Regression-tested (`tests/unit/test_api.py::TestWeeklyRankingsSurfaceEvidenceAdjustment`, 3 new
cases, including one proving the sort order uses the adjusted value and not the base value --
the whole point of this change). 287 offline tests passing (up from 284).

## D47 — Real task decomposition/dependency discovery for the orchestrator (P7)

`docs/CURRENT_STATE_AUDIT.md`'s honest finding: "the DAG shape is fixed/declared, not
dynamically planned" -- `orchestrator.py::run_pipeline` already does real dependency resolution,
retry/backoff, and genuine concurrent dispatch (unit-tested, unchanged, not touched here), but
every caller had to hand-type a `list[Task]` with `depends_on` edges themselves; the only
existing example (`orchestrate demo`) was a fixed 2-task demo. Per the P7 instructions this was
scoped to work on ("only after the more important product/data/model gaps are addressed" --
true after D41-D46) and explicitly NOT to replace the scheduler with a new framework.

Added `agents/planner.py::plan_full_refresh`: given a high-level goal (season range, which
optional stages to include), builds the real multi-task graph -- selecting which of the 8
functional agents in `AGENT_REGISTRY` apply (AGENT_CONTRACTS.md's "select appropriate agents")
and wiring each one's `depends_on` to the real upstream task it actually needs
(AGENT_CONTRACTS.md's "dependencies are explicit"), read directly off what each agent's
`registry.py` implementation queries/writes rather than guessed -- e.g. `market_edge` depends on
`projection_ml` because `market/edge.py`'s EDGE build reads `uncertainty_predictions`, which
only `projection_ml`'s `run_uncertainty` call writes; `rookie_ml` depends only on `identity`
(not on `projection_ml`), which is what makes it genuinely eligible to run concurrently with
projection rather than being forced to wait on it. Also auto-schedules one `evaluation_qa`
review task per position after `projection_ml` (AGENT_CONTRACTS.md's "invoke critique") --
previously QA review was a fully separate, never-auto-invoked path.

This is explicitly declarative dependency-graph construction, not an AI planner and not a new
execution model -- `run_pipeline` itself is byte-for-byte unchanged. Disclosed limitation, not
silently dropped: disagreement detection (`agents/disagreement.py`) is not yet auto-scheduled as
a dependent task -- it remains the separate `orchestrate disagreements` command, since wiring it
in correctly (it needs both `projection_ml` and `market_edge`'s *committed* output, and its own
result shape doesn't fit the `Task`/`Result` contract without changes to `disagreement.py`
itself) was judged a real follow-up rather than something to do half-correctly under this pass.

Added `alpha-squad orchestrate run` (planner-powered; `orchestrate demo` untouched, still the
original minimal 2-task example). **Verified against the real database**, not just stub agents:
`alpha-squad orchestrate run --run-id planner-verify-1 --season-start 2025 --season-end 2025
--min-train-season 2020 --no-include-evidence --no-include-qa` completed all 5 real tasks
(data → identity → {rookie, projection} → market-edge) -- the completion order in the printed
report shows `rookie` finishing before `projection` despite `projection` being declared first,
confirming they genuinely raced concurrently rather than running in declaration order, and
`market-edge` correctly only started after `projection` had actually committed
`uncertainty_predictions`.

Regression- and integration-tested (`tests/unit/test_planner.py`, 12 new cases): structural
tests on the generated graph's edges, plus tests that actually run the generated plan through
the real `run_pipeline` with stub agents (same pattern `test_agents.py`'s existing orchestrator
tests use) -- including one proving `rookie_ml`/`projection_ml` start within 0.2s of each other
(genuine concurrency, not accidentally-sequential) and one proving `market_edge` never starts
before `projection_ml` completes. 299 offline tests passing (up from 287).

## D48 — Auto-detect the newest season with real data (`GET /seasons/latest`)

Six frontend views (`RankingsView` x2, `EdgeView`, `EvidenceView`, `LeagueView`, `TradeView`,
`WaiverView`) hardcoded a season default (mostly `2025`, one inconsistently `2024`) -- the same
failure mode D40 already fixed once for the rookie-class default (a hardcoded value silently
going stale every season rollover; `EvidenceView`'s already-inconsistent `2024` while everything
else said `2025` was itself a small real symptom of this). Added `GET /seasons/latest`
(`api/routers/seasons.py`) returning the real max season per relevant table
(`uncertainty_predictions`/`weekly_projection_snapshot`/`edge_snapshot`/`evidence_events`), and
one shared frontend hook (`web/src/hooks.ts::useLatestSeason`) instead of six components each
re-implementing the same fetch-on-mount-with-fallback (ACCEPTANCE_CRITERIA.md: no duplicated
logic). Regression-tested (`tests/unit/test_api.py::TestLatestSeasons`, 2 new cases, including
the empty-database case returning null rather than erroring).

**A correction, recorded for the record rather than silently edited away.** While verifying this
live, `data/alpha_squad.duckdb` briefly read back as completely empty (every table 0 rows) even
though this same session had just confirmed real data in it multiple times over (25,052 real
players from an `orchestrate run` identity build, 453 real uncertainty predictions, 291 real
evidence deltas -- all still accurate as historical records of what those runs produced, D43/D46/
D47). I investigated at the time (ruled out a destructive `DELETE`/`TRUNCATE` anywhere in `src/`,
a stray `.wal` file, an un-isolated test `Settings()` call, orphaned processes, a `TMPDIR`/
symlink misconfiguration) and, unable to find a code-level cause, wrote an entry here concluding
"unexplained data loss." That conclusion was wrong: the harness reported a container restart
immediately afterward, and re-checking `data/alpha_squad.duckdb` right after confirmed all of it
-- 25,053 real players, 26,816 player-seasons, 2,271 uncertainty predictions, 1,543 EDGE rows,
19,061 evidence events, 684 dynasty values -- fully intact. The empty read was a transient
artifact of the restart (the persistent volume momentarily unavailable/remounting), not real data
loss, and definitely not something this session's code or commands caused. Leaving the original
"unexplained data loss" conclusion in this log would have been an inaccurate permanent record;
correcting it here (rather than deleting the paragraph, since docs/DECISIONS.md is append-only)
is what CLAUDE.md's "no untested claims" standard requires once better evidence exists.

## D48 addendum — Made `GET /players` genuinely reachable (`PlayerPicker`), and a real bug found doing it: `<label>` around a nested interactive picker resets its own state on click

A dead-code check (Explore sub-agent, application-hardening pass) found `GET /players`/
`GET /players/{id}` had a working backend route *and* a working `api.ts` client wrapper
(`listPlayers`/`getPlayer`) that nothing in the UI ever called -- every form asking for a
`player_id` (Waiver, Trade) made a user type the raw opaque canonical id (`asq_<hash>`) by hand,
against a placeholder (`"00-0012345"`) that did not even match that format. `GET /provenance/
{entity_id}` and `POST /league/{id}/trade-package` were found unreachable from the UI too, but
`trade-package` is real and CLI-live (D45, not dead, just not yet UI-exposed -- a smaller, disclosed
instance of the same "built but unwired" pattern D44 already fixed for waiver/trade/roster-need),
and `provenance` is closer to `/rankings/weekly`'s "why did this change" story than to a delete
candidate. Rather than deleting a working, spec-relevant capability (`players` search) or leaving
it permanently dead, wired it in: `web/src/components/PlayerPicker.tsx`, a real name-search
autocomplete (debounced `GET /players?q=`) wired into `WaiverView`/`TradeView`'s player fields.

**A real bug found and fixed while verifying it live** (not a synthetic test -- caught by driving
the actual app in Playwright): wrapping `<PlayerPicker>` in a real HTML `<label>Player
<PlayerPicker .../></label>` (matching every other `.controls` field's existing pattern)
caused clicking a search result inside the picker's own dropdown to silently reset the picker's
selection state back to empty on every pick, immediately after correctly selecting it -- verified
via a render-logging build showing the correct `{selected: "asq_...", value: "asq_..."}` render
immediately followed by `{selected: undefined, value: ""}` with no user action in between. Root
cause: HTML's implicit label-click-forwarding -- clicking anywhere inside a `<label>` also
activates/refocuses the first descendant form control, which raced against `PlayerPicker`'s own
`onClick`-driven state update. `PlayerPicker` nests an `<input>` plus a clickable `<li>` list,
exactly the "multiple/nested interactive elements inside one label" pattern the HTML spec warns
against. Fixed by wrapping the field in a plain `<span className="picker-field">` (matching
`.controls label`'s layout via CSS instead of the `<label>` element itself) rather than papering
over it with `stopPropagation()` inside the picker.

**Verified end-to-end in a real browser** (Playwright, real backend + frontend, real data):
searched "Mahomes", picked the real result, submitted a real waiver recommendation for week 8 --
got back a real FAAB bid ($17.14), real meaningful-role probability (0.98), and real reasons
(marginal value, roster fit, competing-bid likelihood, dynasty value), with a real decision
recorded (`dec_914f2d93508d4252`). 301 offline tests unaffected (frontend-only change; no new
backend surface, `GET /players` already existed and was already tested).

## D49 — Wire the Monte Carlo simulation engine into the API/UI (closes P1-4); found and fixed the real reason it always reported "not enough history"

`models/simulation/correlated.py::simulate_team_season` was real, tested, and CLI-only
(`alpha-squad simulate team-season`) -- the last of the four "built but invisible" capabilities
this hardening pass set out to close (waiver/trade/roster-need closed D44/D48; this was the
remainder). Added `POST /simulate/team-season` (`api/routers/simulate.py`) wrapping the exact
same function the CLI calls -- no parallel simulation logic -- persisting via the existing
`record_simulation_run` and enriching player rows with `display_name` via a `players` join, the
same pattern `edge.py` already uses. Frontend: `SimulationView.tsx`, a new "Simulation" tab
(team/season/n_simulations inputs, a "Run simulation" button since a real Monte Carlo run is
real compute, not a cheap read -- POST, not GET, matching the CLI's own one-shot-command
treatment of it). `tests/unit/test_api.py::TestSimulation`, 2 new cases (a real synthetic-history
run proving the endpoint round-trips through `simulate_team_season` and persists a
`team_simulation_runs` row; a 422 for insufficient history rather than a fabricated result).

**A real, separate gap found verifying this against the live database, not a synthetic test:**
every team/season combination reported "not enough real history" regardless of team, because
`team_week_points` (the real final-score table `_team_environment_history`'s covariance draw is
calibrated against) was completely empty in this deployment -- 0 rows. `models/simulation/
team_scores.py::build_team_week_points` (real, tested against a mocked pbp snapshot in
`tests/integration/test_simulation_live.py`) existed but had never been wired to any CLI command;
an earlier session's D8/D29 note describes backfilling it, but that was a one-off ad-hoc
invocation, not a reproducible step, and did not survive this database being rebuilt since (D39's
full pipeline rebuild ran `sources ingest`/`identity build`/`features build` but had no step that
would have populated it). This violates CLAUDE.md's "reproducible from `alpha-squad ingest`"
standard for a real, load-bearing table, not just a preseason cosmetic gap -- so fixed the root
cause rather than working around it: added `alpha-squad features build-team-scores` (a thin CLI
wrapper around the existing function, mirroring `build-college-usage`'s pattern) and a
`make team-scores` target between `features` and `market` in both the `Makefile` and `README.md`'s
runbook. Ran it for real: `team_week_points` now has 7,326 rows (season 2012-2025), exactly
matching `team_week_stats`'s row count for the same real pbp-derived source.

**Verified end-to-end, twice:** CLI (`alpha-squad simulate team-season --team KC --season 2025
--n-simulations 500`) returned a real result -- mean team points 433.1 (std 41.3), qb_wr1_correlation
0.345 -- over real 2012-2024 KC history. Then the same thing through the running app (Playwright,
real backend + frontend, real data): searched nothing (team is a free-text abbreviation, no
picker needed for 32 known values), ran KC/2025/1000 simulations, got back real named players
(Patrick Mahomes 354.6 mean QB points, Travis Kelce 222.8 TE, Rashee Rice 172.6 WR, ...), a real
QB/WR1 stack correlation (0.335), and a real persisted run id (`sim_8cd9bd68d07e31c8`) --
screenshot-verified. 303 offline tests pass (301 + 2 new); `make lint` clean.

**Scope note:** this closes P1-4, the last item in `docs/IMPLEMENTATION_GAP_ANALYSIS.md`'s
"built but invisible" list. What's left in that file after this (P2-3 network-suite-in-CI,
P3-1 CLAUDE.md's stale data-source note, P3-2 expert-accuracy weighting) are all disclosed as
low-risk/low-urgency, and P0-1 needs no further code (a user conversation about key rotation,
not engineering work) -- see that file's own "Notes on sequencing" section, updated alongside
this entry.

## D50 — Refresh CLAUDE.md's stale data-source-status note (closes P3-1)

Pure documentation, no code risk, exactly as flagged in D49's "Notes on sequencing." CLAUDE.md's
`## Data` section still described Sleeper/FantasyPros/CFBD as blocked by this environment's
egress policy (citing only D3, the original 2026-08-20 probe) -- stale since D31 (2026-08-22, the
policy itself changed) and D36/D37 (2026-08-23, `CFBD_API_KEY`/`FANTASYPROS_API_KEY` supplied and
confirmed live). Re-verified with a fresh `alpha-squad sources status` run before editing (not
assumed from old docs): all three report `AVAILABLE` right now, alongside every nflverse/
DynastyProcess/cfbfastR/ffopportunity dataset. Only KeepTradeCut (no formal adapter, a site not
an API) and the ESPN public API (an app-level 403, unused either way) remain unreachable, and
neither is required by PRODUCT_SPEC.md's core outputs. Rewrote the note to match
`docs/DATA_SOURCES.md`'s current narrative, cite D31/D36-D38 alongside D3, and keep the
"re-verify with `sources status`" instruction (still good practice, since the policy has already
changed once and may again). No code changed; 303 offline tests and lint unaffected.

## D51 — Expert-accuracy weighting: measured with real live data, confirmed LIMITED (closes P3-2)

`ACCEPTANCE_CRITERIA.md`: "Expert weighting uses demonstrated accuracy where data permits."
`PRODUCT_SPEC.md`'s Market section calls for "expert rankings weighted by demonstrated accuracy."
D4 (this project's first session) marked this LIMITED on the reasoning that individual expert
identity requires the (then-blocked) FantasyPros API. That blocker is gone (D37) -- **re-checked
with a real live call against the paid API this session**: `consensus_rankings` returns
`rank_ecr`/`rank_min`/`rank_max`/`rank_ave`/`rank_std`/`total_experts` per player, never a
per-expert breakdown or expert identity. Confirmed empirically, not assumed: FantasyPros's public
API tier (even paid, even live) does not expose which named expert contributed which rank, only
consensus statistics -- so true per-expert weighting remains genuinely unbuildable with data this
project can access, not merely unbuilt.

`market_snapshot.ecr_best`/`ecr_worst` (real per-player min/max rank across the anonymous experts
behind DynastyProcess's historical ECR series) is the coarser signal "where data permits" actually
allows: how much the experts contributing to a consensus rank agree with each other. Rather than
assume this dispersion doesn't predict anything (or assume it does and wire it in), **measured
it** against real outcomes, reusing this project's own already-tested infrastructure end to end:
for every preseason `rsf` snapshot with a real season to compare against (2022-2025, n=1,925 real
player-seasons), computed the real `ecr_worst - ecr_best` spread and the real relative error
between `_market_implied_points_curve`'s (already-tested, D8/M8) implied points and real
`player_season_stats.total_fantasy_points_ppr`, then split each rank tercile at its median spread
and compared tight-consensus vs. wide-consensus relative error (Mann-Whitney U):

| Rank tier | n | tight-consensus mean rel. error | wide-consensus mean rel. error | p-value |
|---|---|---|---|---|
| Top 50 | 200 | 0.294 | 0.296 | 0.804 (no effect) |
| 51-150 | 397 | 0.342 | 0.424 | 0.006 (tight is *more* accurate) |
| 151+ | 1,323 | 0.753 | 0.671 | <0.001 (tight is *less* accurate) |

The raw pooled spearman(spread, relative error) looked promising at first (-0.34) but that number
is confounded by rank itself (both spread and relative error independently correlate with rank) --
the rank-tier-controlled comparison above is the real test, and it **reverses sign** between the
51-150 and 151+ tiers. There is no consistent, monotonic, generalizable relationship between
expert-consensus tightness and market accuracy in the real data. Applying the same standard this
project already committed to for exactly this situation (D39's pre-registered "measure, and if the
signal doesn't hold up, say so rather than force it in"): **not adopted.** No change to
`edge.py`'s market-rank computation or gating logic -- the existing hard rule (rank AND points
edge must agree, D21) is untouched, and no unreliable weighting was added on top of it.

**Reproduction:** for each season with both a preseason `rsf` `market_snapshot` and
`player_season_stats`, join on `player_id`, compute `ecr_worst - ecr_best` and
`abs(actual - curve.predict(ecr_rank)) / max(curve.predict(ecr_rank), 20)` using
`market/edge.py::_market_implied_points_curve`, then split by rank tercile at the median spread
within each tercile and compare with `scipy.stats.mannwhitneyu`. No new permanent module was
added for this -- unlike D39's rookie ablation, there is no adopted feature to build ongoing
comparison infrastructure around, and adding one for a rejected hypothesis would be exactly the
unnecessary complexity CLAUDE.md's engineering standards warn against. `docs/TRACEABILITY.md`
updated to mark this criterion LIMITED with this empirical justification, replacing D4's original
data-availability-only reasoning. No code changed; 303 offline tests and lint unaffected.

## D52 — Final validation: re-ran the full live/network integration suite after the D41-D51 pass

Section 17 of this hardening pass's directive calls for re-running live/network integration
tests as part of final validation, not just trusting that nothing broke. None of D41-D51 touched
a source adapter, but this hadn't been directly re-confirmed against real external services since
before this pass started, so ran it for real rather than assuming: `make test-network` (`pytest -m
network`, real calls to nflverse/DynastyProcess/cfbfastR/ffopportunity/Sleeper/FantasyPros/CFBD,
no mocks) -- **41 passed, 1 skipped, 0 failed**, ~25 minutes. The one skip is
`test_sleeper_league_context_live.py`'s test needing a specific real league config not present in
this environment, an expected/pre-existing skip, not a new failure. This reconfirms every
live-source claim made across D41-D51 (Sleeper/FantasyPros/CFBD availability, the real KC 2025
simulation, real league workflows, etc.) against actual external services at the end of the pass,
not just at the moment each was first built. Closes the "run relevant live integration tests"
final-validation step; no code changed.

## D53 — User-facing productization: connect a real league, get real recommendations, with explanations

M12/M14 (D41-D52) had already built the intelligence and exposed most of it behind API endpoints,
but there was no coherent path for an actual fantasy manager to connect their real league and be
told what to do — the audit's own framing ("substantial but partially inert"). This phase's
explicit brief: **connect, understand, analyze, decide, explain** — and "your job is to CONNECT
AND PRODUCTIZE," not rebuild. Every number in every new view below is a direct read of an
already-tested M1-M13 table or a direct call into an already-tested M10 recommendation function;
no new scoring/decision logic was written anywhere in this pass, frontend or backend.

**New real capability, not previously reachable by any user:**
- **Runtime league onboarding** (`POST /league/register`, `league/context.py::register_sleeper_league`):
  validates a Sleeper league is real and reachable (a live fetch) before persisting it to a new
  `registered_leagues` DB table, distinct from the curated `registry.yaml` set — a league
  connected this way is immediately usable everywhere else in the app. `ConnectLeaguePanel.tsx` is
  the UI for this; `alpha-squad league register-sleeper` is the CLI counterpart.
- **Real roster import** (`league/roster_import.py::fetch_sleeper_rosters`): pulls real
  `/league/{id}/rosters` and `/league/{id}/users` from Sleeper (two endpoints added to
  `sources/sleeper.py`'s `_ENDPOINTS`), bridges Sleeper's numeric player ids to canonical
  `asq_<hash>` ids via the existing `player_id_map` crosswalk, and persists a snapshot. Backs
  `GET /league/{id}/teams` and every roster-aware endpoint below.
- **My Team / roster intelligence** (`league/roster_intelligence.py::build_my_team_report`,
  `GET /league/{id}/my-team`): the real roster joined with real uncertainty/EDGE/dynasty-value per
  player, with starter/bench computed by reusing M10's `compute_league_starters` scoped to a
  synthetic one-team league — the exact same value-based-drafting algorithm the whole-league
  calculation uses, applied to just the user's own roster rather than a second implementation.
- **Drop candidates** (`recommend_drops`, `GET /league/{id}/drop-candidates`): worst-VORP bench
  players, structurally excluding anyone the same M10 algorithm marked a starter.
- **Action Center** (`build_action_center`, `GET /league/{id}/actions`) — the phase's own framing
  of "most important user-facing feature": ranked ADD (FAAB dollars)/DROP (VORP)/TRADE (rank-edge)
  lists. Deliberately three separately-ranked lists, not one fabricated cross-type score — ADD,
  DROP and TRADE signals are different units (dollars, replacement value, rank movement) and
  forcing them onto one scale would be exactly the untested precision CLAUDE.md warns against.
- **Batch waiver ranking** (`rank_waiver_targets`, `GET /league/{id}/waiver-targets`): the same
  `recommend_waiver_pickup` M10 function run across a VORP-prefiltered candidate pool
  (`DEFAULT_WAIVER_PREFILTER_N = 80`) instead of one player at a time, so the Action Center's ADD
  list and the standalone Waiver tab are both real ranked output, not a single-player tool
  pretending to be a list.
- **Player Detail** (`GET /players/{id}/detail`, `PlayerDetailView.tsx`): the phase's explicit
  requirement to distinguish **universal player value** (projection/uncertainty/market/EDGE/
  evidence/rookie info — the same everywhere) from **my-league value** (dynasty trade action,
  roster fit — genuinely different per league for the same player) in one view, both computed by
  existing endpoints/functions and merged, not recomputed.
- **Draft view** (`DraftView.tsx`), **Dashboard** (`DashboardView.tsx`), and an upgraded **Trade**
  view (`TradeView.tsx`) adding real multi-asset package evaluation (`evaluate_trade_package`,
  D45) with an ACCEPT/REJECT/CONSIDER verdict phrased from the user's chosen side — all thin
  presentation over existing endpoints; `available_player_ids` in `DraftView.tsx` is the one
  client-side computation in this whole pass, and it is pure set-subtraction (already-ranked
  players minus already-drafted), not a decision.
- A shared `LeagueProvider`/`useLeague()` React context (league id, roster id, real team list,
  localStorage-persisted per league) replaces every view independently holding its own league
  dropdown, and a `PlayerSelectionProvider`/`PlayerLink` context lets any player name anywhere in
  the app jump straight to its Player Detail tab.

**Five real bugs found by exercising the real app end to end (Playwright against the real backend
and a real Sleeper league, `boys_of_fall`), not by code review — every one reproduced, root-caused,
fixed, and covered by a regression test verified to fail without the fix:**

1. **`init_db` (DDL migrations) ran on every request**, not once. `api/deps.py::get_db()` called
   `init_db(con)` per-request; two concurrent requests racing on `ALTER TABLE` raised a real
   `TransactionException: write-write conflict`. Fixed by moving `init_db()` into a new FastAPI
   `lifespan` (`api/app.py`) that runs it exactly once at startup.
2. **`build_action_center` re-fetched the live Sleeper roster 3-4 times per request** — its three
   sub-calls (`rank_waiver_targets`, `recommend_drops`, `build_my_team_report`) each independently
   called `teams_for_league`. Fixed by threading an optional `teams: list[TeamRoster] | None`
   parameter through all three so `build_action_center` fetches once and passes it down;
   regression test asserts exactly one `/rosters` fetch.
3. **`duckdb.connect()` itself is not safe to call concurrently against the same file** — two
   requests arriving close together raised a real `BinderException: Unique file handle conflict`.
   Fixed by opening one shared base connection at lifespan startup and deriving per-request
   connections via `base_connection.cursor()` — DuckDB's own documented-safe way to hand out an
   independent connection per request from one already-open database, confirmed via
   `tests/unit/test_api_concurrency.py`'s `ThreadPoolExecutor`-driven regression tests against a
   real `TestClient(app)` lifespan (not the `dependency_overrides` pattern the rest of the API
   suite uses, which never exercises this code path at all).
4. **`sleeper.py`'s league-scoped snapshot filenames omitted every param** — `league`/
   `league_rosters`/`league_drafts`/`league_users` all wrote to `captured_at=<date>/<dataset>.json`
   with no `league_id` in the path, so registering a second real Sleeper league collided with the
   first's file on disk. The exact same class of bug had already been fixed in `cfbd.py`/
   `fantasypros.py`/`file_release.py` (an earlier `param_suffix` fix); `sleeper.py` was missed
   because its league_id-taking endpoints were added afterward. Found live as a `JSONDecodeError`
   reading a snapshot the registration flow had just corrupted; fixed with the same
   `param_suffix` pattern; regression test in `tests/contracts/test_source_adapters.py`.
5. **`dest.write_bytes(resp.content)` in `sleeper.py`/`cfbd.py`/`fantasypros.py` is not atomic** —
   it truncates the destination file in place, so a concurrent read can observe a torn (empty or
   partial) file mid-write. This matters even after fixing #4, because two different registered
   `league_id`s can point at the *same* underlying real Sleeper league (identical snapshot key),
   so a concurrent read genuinely does race a concurrent write for that key in normal use — still
   observed live as `JSONDecodeError: Expecting value: line 1 column 1` after #4 was fixed.
   Reproduced directly: hammering the old `dest.write_bytes()` pattern with concurrent
   writer/reader threads over ~2,000 reads against one shared 5KB file produced **5,292 torn
   reads**; the same test against the fix produced zero. Fixed with a new
   `sources/base.py::write_bytes_atomic()` (write to a uniquely-named temp file, then
   `Path.replace()` — atomic on the same filesystem) — the pattern `sources/http.py`'s
   `http_get_to_file` already used, now applied to the three adapters that instead wrote in
   place. Regression test in `tests/unit/test_source_base.py`, verified to fail reliably (every
   run) against the old pattern and pass reliably against the fix.
6. **A UI-only bug**, not a backend one: `ConnectLeaguePanel.tsx` called `onConnected()` (which
   sets `showConnect=false` in the parent, unmounting the panel) in the same synchronous state
   batch as `setConnected(result.league_id)`, so React committed the parent's re-render — panel
   already gone — before the "Connected as ..." confirmation message the user is meant to see
   ever painted. The registration itself always worked; the confirmation just never appeared.
   Fixed with a 1500ms `setTimeout` before `onConnected()` so the message has a beat on screen.

**Live verification**, all against the real `boys_of_fall` Sleeper league (a real 2QB dynasty
league) through the real backend, via Playwright driving real Chromium against real dev servers —
not mocked intelligence: register a brand-new league through the actual Connect League form and
confirm it persists into the league dropdown; My Team roster intelligence; Action Center adds/
drops/trade signals; Player Detail (universal + my-league value + a real 10-row evidence
timeline); Draft recommendation (real VORP/confidence/survival-probability); standalone Waiver
tab producing a real FAAB bid with real reasons; multi-asset Trade package (two players + a future
pick per side) producing a real ACCEPT/REJECT/CONSIDER verdict with real side values and reasons.

**Explicitly not built:** a manual/YAML league (`source: yaml`) has no runtime "connect" flow —
`teams_for_league` returns `None` rather than fabricating roster data for it, and the UI shows
"no real per-team roster data" instead of a broken or fake roster view, consistent with this
project's standing rule against fabricated data.

350 offline tests passing (up from 303 at the start of this pass); `make lint` clean
(ruff + `check_no_secrets.py`); TypeScript compiles clean (`tsc --noEmit`).

## D54 — Empirical validation phase: methodology committed before results (results appended below)

M15 productized the intelligence; this phase asks the harder question directly: does Alpha's
intelligence actually produce better fantasy-football decisions than strong, reasonable
baselines? Per the phase's own explicit instruction ("do not tune the evaluation methodology
after seeing results... do not cherry-pick... if a simple baseline beats Alpha, report that
honestly"), this entry's methodology section was written and committed *before* any of this
phase's evaluation commands were run against real data — the same pre-registration discipline
D39 established for the rookie-ablation decision rule, now applied phase-wide.

**New package**: `src/alpha_squad/evaluation/` — `config.py` (versioned config stamped into
every report), `projection_benchmark.py`, `market_inefficiency.py`, `draft_simulation.py`,
`waiver_evaluation.py`, `rookie_benchmark.py`, `dynasty_validation.py`, `trade_evaluation.py`,
`failure_analysis.py`. Every module is also an `alpha-squad evaluate <name>` CLI command. See
`docs/EVALUATION_PLAN.md` for the full design and `docs/EVALUATION_LIMITATIONS.md` for what
this environment's real data genuinely cannot support (no historical FAAB-bidding log, no
historical dynasty-value time series, no ADP series, no historical back-series for FantasyPros
point projections — each traced to a specific real gap, not assumed).

**Committed before results, not adjusted after:**
- Market-inefficiency 5-tier thresholds: `|rank_edge| >= 6` mild, `>= 16` strong, confidence
  `>= 0.75` high-confidence; BUY/SELL actions (already evidence-gated by D21) are the
  evidence-backed tier by construction.
- Waiver-tier pool: real preseason overall ECR rank `> 150` (or no consensus rank at all) =
  "a standard league wouldn't have rostered this player." Top-K = 20.
- Draft simulation: one team (every one of the league's 10 slots, once per season) drafts
  under the strategy being tested; the other 9 always draft real historical market consensus
  (best-remaining-ECR) — a fixed, realistic opponent field so only the team-in-question's
  strategy varies across trials. Four strategies: `market_consensus`, `generic_prior_year`
  (real prior-season points, a non-market generic ranking), `alpha_bpa` (Alpha's own
  predicted points, no league context), `alpha_league_aware` (the real `recommend_draft_pick`).
  Real seasons 2021-2025 (`uncertainty_predictions`' actual walk-forward coverage) — not
  widened to make the sample look bigger, not narrowed to exclude an inconvenient season.
- Dynasty heuristics: draft classes 2012-2023 for pick-value (needs 3 real post-rookie
  seasons per class), 2012-2025 for age curves, both against real `player_season_stats`.

**A real bug found building this phase's own report generator, before it ever touched
production data:** `projection_benchmark.py`'s first draft derived every model's position
purely from its *name* (Alpha's season-level models encode position in the model name,
e.g. `ml_season_catboost_wr`), which silently mapped every baseline's row to
`position='ALL'` regardless of its real per-position value in the `position` column — baselines
would never have appeared in the by-position comparison table at all. A second bug: the
season-intersection check only intersected model families that had *any* row, so a model
family with zero rows anywhere (which should force the whole comparison to LIMITED/empty)
was silently excluded from the intersection instead of correctly emptying it. Both caught by
`tests/unit/test_evaluation_projection_benchmark.py`, written before this phase's report was
ever run against the real database, and fixed before any real number was reported.

### Results

All eight `alpha-squad evaluate <name>` commands were run against the real database (real
seasons, no synthetic substitutions); full numbers, per-section detail, and the eleven
directive questions answered directly are in `docs/ALPHA_VS_BASELINES_EVALUATION.md`. Summary,
reported exactly as found — two of these are unfavorable to Alpha's current implementation:

- **VALIDATED.** `ml_season_catboost` has the lowest MAE of any model (baseline or Alpha) at
  every position (QB/RB/WR/TE), real 2021-2025 window — Alpha's underlying player-value model
  is genuinely good. The EDGE evidence gate (D21) is also validated directly: the 5-tier
  market-inefficiency breakdown shows raw disagreement magnitude alone (tiers 1-3, no gate) is
  *not* monotonic with outcome, while the evidence-gated BUY/SELL tier is clearly positive —
  the gate is doing real work, not just adding friction. Pick-value's (D45) directional
  assumption is also confirmed: real rookie-season points decline monotonically across all 7
  real draft rounds.
- **PROMISING.** EDGE's BUY signal beat the market in 3 of 4 scored seasons (2022-2024),
  though 2025 was its first negative season on record. Alpha's rookie model beats every
  baseline specifically in late rounds (5-7, MAE 28.7 vs. best baseline 30.4), where draft
  capital alone is a weak signal.
- **FAILED, with an identified, actionable root cause — the headline unfavorable finding.**
  `alpha_league_aware` (the real `recommend_draft_pick`, used in a historical draft
  simulation against a fixed market-consensus opponent field) lost to plain
  `market_consensus` on mean starter points in **every one of the 5 real seasons tested**
  (2021-2025; pooled 1644.5 vs. 2020.7) and never won a single season outright. On pooled
  *total* roster points it also scored below `alpha_bpa` (identical player values, no league
  context: 2680.0 vs. 2756.1) — though it *beats* `alpha_bpa` on pooled *starter* points
  (1644.5 vs. 1429.1), a real, mixed nuance: league context measurably improves the started
  lineup, it just also strands more value on the bench overall (see the root cause below).
  Root-caused not just by inspecting the final drafted rosters but by *replaying* the real
  `recommend_draft_pick` function pick-by-pick against real 2021 data (prompted by a direct
  question of whether "7 QBs, 0 RBs" was even plausible for a real draft — it is, and the
  replay shows exactly why): `alpha_league_aware` drafted 7 QBs and zero RBs (of 17 picks,
  into a league starting 2 of each) in one real 2021 trial, and 12 WRs against only 3 QBs in a
  real 2025 trial. Two compounding mechanisms, not one: (1) `roster_fit_multiplier` is bounded
  to [0.7, 1.3] by design, but its real penalty growth is far gentler than that bound implies
  — even after already drafting 6 QBs, a 7th costs only a 6% discount (`fit_mult=0.94`,
  verified by direct computation), nowhere near the 0.7 floor, and nowhere near enough to
  overcome a real VORP edge (round 1 of the replayed draft: an available TE at 127.5 VORP and
  QB at 131.2 both beat the best available RB at 103.1, before any need adjustment); (2) the
  other 9 real market-consensus opponents drain the RB pool at a normal rate throughout, so by
  round 16 the best *available* RB had VORP -135.4 (worse than replacement) — by the time
  roster-need pressure would organically demand an RB, none were left to correct with. This is
  a decision-logic bug in how good player values become a 17-pick sequence, not a modeling
  problem (§1 shows the values themselves are good) — the most actionable finding of this
  phase.
  **This finding was independently re-verified after the fact**, prompted by a direct question
  about whether the evaluation was genuinely leak-free: found and fixed two real bugs in the
  draft-simulation path itself (not methodology changes) — `next_pick_survival_probability`
  had no season scoping at all (a historical draft could see market data from years later),
  and `min`/`max`/`.sort()` tie-breaks over Python `set`s had no secondary key, which is
  non-deterministic across process runs because `PYTHONHASHSEED` is unset here and real ties
  are common in the data. Both fixed with regression tests; the simulation was then re-run
  twice in separate processes and produced byte-identical reports, confirming the corrected
  numbers above are genuinely reproducible. The one factual correction this required: an
  earlier draft of this document claimed `market_consensus` won outright in all 5 seasons —
  it actually wins 4 of 5, with `generic_prior_year` (a non-market baseline) edging it out in
  2025 specifically. `alpha_league_aware` still never wins any season, so the core finding is
  unchanged and now rests on firmer ground.
  **A fix for mechanism (1) above was implemented and re-verified against a full re-run, per
  explicit request, rather than left as a documented-but-unfixed finding.**
  `roster_need`'s oversaturation coefficient was steepened (-0.2 -> -3.0 per player beyond
  starters + a healthy 2-deep bench) so `roster_fit_multiplier` hits its 0.7 floor immediately
  at one player past a full bench, instead of requiring ~15 extra players. Re-running the full
  evaluation: `alpha_league_aware`'s pooled starter points improved 1644.5 -> 1688.2 (+2.7%,
  a real gain in the metric that determines actual fantasy outcomes) and the 2021 slot-1
  roster's QB count dropped 7 -> 6, but pooled total points *worsened* 2680.0 -> 2606.6
  (-2.7%, a real tradeoff: less value stranded on the bench of an over-drafted position, but
  the roster leans on lower-value players at other positions to get there). **The fix does not
  close the gap**: `alpha_league_aware` still loses every one of the 5 seasons on starter
  points (0/5, unchanged) and still trails `market_consensus` by 332.5 pts pooled (down from
  376.2 — roughly 12% of the original gap closed). The 2021 slot-1 roster still drafted **zero
  RBs** even after the fix, directly confirming mechanism (2) (positional-scarcity blindness)
  is untouched — a same-position saturation penalty cannot help a position the engine never
  drafted at all. The 2025 slot-1 roster did rebalance meaningfully (RB count 1->2, WR
  count 12->9), so the fix is a real, partial improvement, not a no-op — just not sufficient
  alone, exactly as anticipated before re-running. Mechanism (2) remains the open item.
- **INCONCLUSIVE.** SELL signal reliability (mixed sign by season); disagreement magnitude
  alone absent the evidence gate; waiver-tier value discovery as a full answer to FAAB quality
  (no historical bidding log exists in this environment — see `docs/EVALUATION_LIMITATIONS.md`);
  the age-curve heuristic's (D25) specific decline ages, confounded by real survivorship bias
  (every late-age cell has n ≤ 8); early/mid-round rookie evaluation vs. draft capital alone.
- **NOT YET EVALUATED.** FAAB bid efficiency and causal trade-outcome attribution — both need
  real transaction/history data this environment does not have.

Four real software bugs were found and fixed *during* this phase, before any result was
treated as final (see above and their own regression tests): the `projection_benchmark.py`
position-misclassification and season-intersection bugs, the draft-simulation leakage and
non-determinism bugs described above, and a `zip(..., strict=True)` crash
in `dynasty_validation.py`/`market_inefficiency.py` that only triggers on a cleanly monotonic
(i.e. "good") result. None of these were methodology changes made after seeing unfavorable
results — the pre-committed thresholds and strategies above were not touched.

## D55 — Positional opportunity cost in the production draft engine (M18)

M17's forensic audit (`docs/DRAFT_ENGINE_FORENSIC_AUDIT.md`) identified the root cause of the
draft engine's roster pathology: `recommend_draft_pick`'s score had no representation of
*positional* opportunity cost — only a single-*player* survival probability, which asks "will
THIS player still be there" and never "will a player THIS GOOD AT THIS POSITION still be
there". This entry records the fix, and — more importantly — why the fix that shipped is not
the one `docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` proposed.

### The recommendation's formula had never actually been measured

Verifying the recommendation against source before implementing it (rather than implementing
it because it was written down) found three *different* formulas in play:

| | Formula |
|---|---|
| Production (pre-D55) | `vorp × fit × risk × survival` |
| Experiment F (the best A-H performer) | `vorp × fit × scarcity × future × [feasibility] + opp_cost` |
| What the recommendation proposed | `production + opp_cost` |

Experiment F **includes** `scarcity_mult` — the one mechanism the controlled experiments proved
actively harmful — plus tiers D and E, and **excludes** production's `risk_mult` and
`survival_mult`. So F's measured result (RB=0 → 4%, starter 1789.1) does not belong to the
formula the recommendation asked for. Shipping it directly would have deployed an unmeasured
combination on the strength of a number that described something else.

Decomposing the existing 400-draft grid sharpened this further: `scarcity_mult` costs −123.6
starter points, `future_mult` −10.6, while the feasibility cap gains +55.0 and the opportunity
cost +134.6. F's headline number is the *net* of a large penalty and two large gains — and the
feasibility cap, which the recommendation barely mentions, is a real contributor hiding inside
it.

### A new pre-registered ablation on the real production base

Rather than guess, six new **P-tiers** were added to the diagnostic harness, holding the actual
production formula fixed as the control and varying only the addition. The decision rule was
written into `evaluation/draft_forensics.py` and committed **before** the tiers were ever run
(the D39/D54 pre-registration discipline): primary metric = mean starter points; gate = RB=0
rate must not exceed production's 10/50; second gate = no position may be zeroed at a higher
rate than production; tie-break = fewer mechanisms. Explicitly: *a tier that improves RB=0
while losing starter points does not qualify.*

Results (300 real drafts, 5 seasons × 10 slots, n=50 per tier):

| Tier | Formula | starter | total | RB=0 | concentration |
|---|---|---|---|---|---|
| P0 | production (control) | 1688.2 | 2606.6 | 10/50 | 0.345 |
| P1 | `P0 + opp_cost` (the recommendation's literal proposal) | 1777.1 | 2673.9 | 6/50 | 0.344 |
| P1b | `P0 + opp_cost × risk` | 1734.8 | 2644.4 | 8/50 | 0.344 |
| P1c | `(vorp + opp_cost) × fit × risk × survival` | 1783.3 | 2617.3 | 5/50 | 0.331 |
| P2 | `P0 × feasibility` | 1706.0 | 2624.0 | 10/50 | 0.315 |
| **P3** | **P1c × feasibility** | **1801.1** | 2599.8 | **2/50** | **0.304** |

P0 reproduces tier H (the real engine) exactly — 2829.8 / 1676.9 on the 2021 slot-1 control,
identical roster — confirming the harness models production faithfully before any conclusion
is drawn from it. All five candidates passed the gates; **P3 won the primary metric outright**
and also beats Experiment F (1789.1) *while excluding `positional_scarcity` entirely* and
retaining production's confidence and survival terms.

### Shipped

```
score = (VORP + positional_opportunity_cost[position]) × fit × risk × survival
        × [0.1 if already at this league's usable positional cap]
```

Three design decisions worth recording, each measured rather than assumed:

- **The cost is added to VORP *before* the multipliers, not to the finished score.** This is
  what prevents it from overwhelming the base: it is denominated in VORP points, so it is
  discounted by the same roster-fit and confidence factors as the value it augments. The raw
  additive form (P1) was measured at **8× the base score** in a real late round (2021 slot 5,
  R13: base 2.4, opp cost 19.3), and scored worse than the integrated form.
- **`positional_scarcity()` is deliberately not used.** It rates QB as the most "scarce"
  position and RB as one of the least in this league's real data — adding it made the pathology
  worse (RB=0 20% → 32%). The requirement in `PRODUCT_SPEC.md` that scarcity "is calculated"
  remains satisfied by the waiver engine, which does consult it; `docs/TRACEABILITY.md` records
  the draft engine's deliberate exclusion.
- **Both sides of the comparison clamp at replacement level.** VORP already measures against
  the waiver floor, so "losing" a below-replacement player costs nothing. Without this, a real
  2021 late-round comparison between two below-replacement RBs (best available at VORP −135.4)
  manufactures a spurious cost. This is a league-derived bound, not a tuned constant.

### Supporting changes

- New `league/opportunity_cost.py`: Experiment G's literal opponent replay feeding Experiment
  F's continuous points pricing, exactly as the recommendation intended — computed **once per
  position per pick**, not once per candidate. That is the mechanism's real shape (the cost is
  a property of the position), and it measured 9× faster with byte-identical results.
- `positional_feasibility_cap` in `league/roster.py`, derived from the league's real
  `bench_size` — which M17 found was dead code, `roster_need` having used a hardcoded
  `slots + 2` unrelated to the configured bench. It stacks with, rather than replaces, D54's
  saturation fix.
- **Two latent determinism bugs fixed** in the diagnostic F/G tiers: `sorted()` calls with no
  `player_id` tie-break, the same bug class D54 fixed in `draft_simulation.py`. Real VORP ties
  exist in production data (2021: 8 tied WR groups covering 17 players). Verified the fix left
  tiers E and F numerically identical, so the M17 documents remain accurate.
- One canonical `best_by_market_rank`, shared by the benchmark's `market_consensus` strategy
  and the replay, so they cannot drift.
- `current_pick_overall` threaded through the benchmark, API, CLI and `DraftView`. When absent
  the term is simply omitted (the engine degrades to P2 behaviour, still measured better than
  the old default) rather than guessing where the draft is.
- Leakage-safe by construction: the replay reads season-scoped preseason ranks via the existing
  `_preseason_overall_market`, the same helper D54 required after finding a real leak of
  exactly this kind.

### Results

Measured with the official `alpha-squad evaluate draft-simulation` benchmark over the full
2021-2025 window, not the diagnostic harness. The benchmark reproduced the P-tier prediction
**exactly** (1801.1 pooled starter points, and every per-season figure to the decimal), which
is itself a useful validation that the harness models production faithfully.

**Headline (pooled, n=50 drafts per strategy):**

| Strategy | starter pts | total pts |
|---|---|---|
| market_consensus | 2020.7 | 2935.1 |
| **alpha_league_aware (D55)** | **1801.1** | 2599.8 |
| *alpha_league_aware (pre-D55)* | *1688.2* | *2606.6* |
| generic_prior_year | 1708.3 | 2882.0 |
| alpha_bpa | 1429.1 | 2756.1 |

**+112.9 mean starter points (+6.7%).** Alpha's draft engine moves from 3rd of four strategies
to 2nd, now clearly ahead of `generic_prior_year` (which it previously trailed). It also beats
Experiment F's 1789.1 while excluding `positional_scarcity` entirely.

**Per season — 4 wins, 1 real loss, reported as found:**

| Season | starter before | after | Δ | total Δ |
|---|---|---|---|---|
| 2021 | 1695.3 | 1825.7 | **+130.4** | −104.7 |
| 2022 | 1699.1 | 1981.8 | **+282.7** | +86.3 |
| 2023 | 1813.3 | 1806.9 | **−6.4** | −100.5 |
| 2024 | 1658.2 | 1795.9 | **+137.7** | +15.3 |
| 2025 | 1575.1 | 1595.4 | **+20.3** | +69.5 |

2023 regresses by 6.4 starter points (0.35%). It is small and it is real; it is recorded rather
than averaged away. Pooled **total** roster points also dip slightly (2606.6 → 2599.8, −6.8) —
an expected and arguably desirable trade, since total points reward bench hoarding, which is the
pathology under study, while starter points are what decide real matchups.

**Roster construction — every feasibility metric improved, none regressed:**

| Metric | before | after |
|---|---|---|
| RB=0 rosters | 10/50 | **2/50** |
| QB=0 / WR=0 / TE=0 | 0 / 0 / 0 | 0 / 0 / 0 (no hole traded for another) |
| Max QB on one roster | 8 | **6** |
| Mean QB per roster | 4.8 | 4.2 |
| Max at any single position | 10 | 9 |
| Concentration index | 0.345 | **0.304** |
| Max single-position share | 0.472 | 0.411 |

The D54 QB-stacking pathology is materially reduced: rosters with 7 or 8 QBs (9 of 50 before)
**no longer occur at all**, and the distribution shifts toward the league's actual 2-QB
requirement (4QB rosters go 9 → 23).

**Draft-slot behaviour: all 10 slots improve, none regress** (+38.8 at slot 10 to +219.5 at slot
3). The gain is not an artifact of one lucky seat.

**Mechanism verified, not just outcomes.** Re-tracing the 2021 slot-1 pathological draft
pick-by-pick (`reports/draft_decision_trace_d55.json`): pick #1 is now **RB**, where it was TE
before, and the engine's own reason string states why — *"RB opportunity cost +60.5 pts (that
much RB value is expected to be gone in the 18 picks before your next turn at #20)"*. The RB
wins at 170.2 despite a **lower** VORP (103.1) than the TE it beat. That is the mechanism doing
exactly what it was built to do, confirmed from the decision trace rather than inferred from the
final roster. In 2025 slot 1 — a season that never had the pathology — the roster is
essentially unchanged (RB count stays 2, starter +5.4), i.e. the term is targeted, not a
blanket re-weighting.

**Honest limitations:**

- **The gap to market consensus is narrowed, not closed** (219.6 starter points remain). D55 is
  a substantial, measured improvement; it is not a claim that Alpha now drafts better than
  following expert consensus. `docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0's acceptance criterion
  is still unmet.
- **2023 regressed** (−6.4). Not diagnosed further in this pass; the effect is within the range
  where a single season's noise is plausible, but it is not dismissed as noise without evidence.
- **The feasibility cap fires on every draft** (50/50 rosters have at least one position over
  cap, before and after). It discourages rather than forbids (0.1x, not 0), so rosters still
  concentrate more than an idealised allocation would.
- **The opponent replay assumes market-consensus opponents.** Exactly true inside the benchmark;
  an approximation against real human drafters — the same class of assumption
  `next_pick_survival_probability` already makes.

**Determinism: PASS.** The full benchmark was run twice in separate processes and the reports
are byte-identical (`md5 d34d5a3deb8ba2be233d7746e5a5a251`). This matters more than usual here:
D54 found a real hash-randomization bug in exactly this harness, and D55 fixed two more of the
same class in the diagnostic tiers. The opportunity-cost term is deterministic by construction —
it maxes over VORP *values*, so tied players cannot change the figure regardless of `set`
iteration order — and the replay uses the canonical `player_id`-tie-broken market pick.

**Runtime: negligible.** Measured against the real 2021 universe (559 candidates):

| | per `recommend_draft_pick` call |
|---|---|
| without the term (`current_pick_overall` omitted) | 2.909 s |
| with the term (18 opponent picks replayed) | 3.008 s |

**+0.099 s (+3.4%).** The 2.9 s baseline is dominated by the pre-existing per-candidate database
round-trips (two queries × 559 candidates), not by anything D55 added — the replay itself is
pure in-memory work costing ~10k comparisons. Computing the cost once per position rather than
once per candidate is what keeps it there; the per-candidate form measured ~9× slower in the
diagnostic harness for byte-identical results.

---

## D56 — A market series is `(ecr_type, page_type)`; `rsf` is the superflex board and the wrong benchmark for a 1-QB format

Two separate problems, found while auditing whether the existing consensus benchmark is
appropriate for the new target format. One is a data-quality bug; the other invalidates the
project's entire recorded draft evaluation.

### `ecr_type` alone is not a rank space (bug)

DynastyProcess's `fp_ecr_history` labels several independently-ranked FantasyPros pages with
the same `ecr_type`. Verified against the real snapshot:

| ecr_type | page_type | FantasyPros page | rows |
|---|---|---|---|
| `ro` | `redraft-overall` | `ppr-cheatsheets.php` | 102,563 |
| `ro` | `redraft-idp` | `idp-cheatsheets.php` | 38,873 |
| `rsf` | `redraft-op` | `ppr-superflex-cheatsheets.php` | 99,694 |

`market/consensus.py` mapped rows to `ecr_type` without filtering the page, so `ro` merged the
PPR draft board with a separately-ranked 1..N IDP board. The two sequences collide — in
preseason 2024, `ro` rank 3.0 was simultaneously an LB and a WR — so "best available by ECR"
could return a linebacker in a league that cannot start one. Worse, the pre-D56 PRIMARY KEY
did not include the page, so one of any two rows a player held on the same date was silently
dropped.

**Fix:** `market_snapshot.page_type`, populated from the real source column and part of the
key, with a migration that carries pre-existing rows across at `page_type = ''` rather than
inventing a page they never recorded. `_preseason_overall_market` defaults its scoping to the
page `market/series.py` maps the `ecr_type` to, so every existing caller was fixed without
threading a new argument through thirty call sites.

`redraft-overall` also carries `ros-ppr-overall.php` (rest-of-season) rows, a genuinely
different product. Verified those appear only in months 9–12, so the July/August preseason
scoping every consumer already applies excludes them by construction.

### `rsf` is the superflex board (format mismatch)

D21 chose `ecr_type='rsf'` deliberately and correctly, because the target league was then 2QB.
`rsf` is FantasyPros' `ppr-superflex-cheatsheets.php`. Measured on the real preseason-2024
snapshot:

| board | QBs in the overall top 15 | first QB |
|---|---|---|
| `rsf` | **9 of 15** | ECR 1.7 |
| `ro` | **0 of 15** | ECR 23.4 |

And on what a consensus draft builds, 10-team snake, 2021–2025 × 10 slots = 50 drafts per
board:

| board | mean QB | mean RB | mean WR | mean TE | share landing on 1–3 QBs |
|---|---|---|---|---|---|
| `rsf` | 4.1 | 5.1 | 6.1 | 1.8 | 20/50 (40%) |
| `ro` | **2.4** | 5.5 | 6.9 | 2.1 | **40/50 (80%)** |

So the claim that a 1-QB redraft team drafts roughly 1–3 QBs is **supported by this project's
own historical consensus data under `ro`**, and is not supported under `rsf`. `ro` also has
better coverage: 211k rows / 3,110 players from 2019-12, against 98k / 1,393 from 2021-01.

**Consequence, stated plainly:** every draft number recorded before this entry — market
consensus 2020.7 starter points, `alpha_league_aware` 1801.1, the −219.6 gap, the M17 forensic
audit, the D55 P-tier ablation — describes Alpha playing a *superflex* league. Those results
remain valid for the league they measured. They are labelled by that format rather than
restated, and they do not transfer to the 1-QB target.

**Design:** `market/series.py` resolves the `(ecr_type, page_type)` pair from the league's own
lineup and format. A superflex lineup — two dedicated QB slots *or* a QB-eligible flex —
selects a superflex board; a dynasty/keeper format selects a dynasty board. Nothing is
hardcoded, so `legacy_2qb_dynasty` still resolves to `dsf/dynasty-op` from its config alone.

## D57 — Kickers and team defenses: computed from real data, projected by measured baselines

The 1-QB target format starts a K and a DEF. Neither was supported, for two different reasons,
both checked against real data rather than assumed.

**Kickers** were ingested (125 of them, back to 2012) but scored **0.0**: nflverse's
`fantasy_points_ppr` prices only passing/rushing/receiving, so all 571 kicker season rows were
zero apart from 7 from incidental non-kicking plays. Every component was present all along —
`fg_made_0_19` … `fg_made_60_`, `fg_missed`, `pat_made`, `pat_missed` — so the points are now
computed from them with Sleeper's documented default scoring (Sleeper being the league source
this deployment actually integrates with, D33/D34).

**Team defenses did not exist as an entity anywhere** — absent from `players`, `player_id_map`,
`player_season_stats`, and `market_snapshot`. They now have canonical ids built from the team
abbreviation (`asq_dst_KC`), never a name, scored from the raw `stats_team_week` `def_*`
columns plus real points allowed from `team_week_points.opponent_points`. The defensive
counting stats live only in the raw snapshot: the normalized `team_week_stats` table keeps
only the offensive-environment columns the projection features need.

A DST has no GSIS id. Rather than relax the identity spine's `NOT NULL` — which DuckDB will
not do while foreign keys reference the table — the `gsis_id` column holds the same
`asq_dst_`-prefixed id, self-evidently Alpha-Squad-generated and incapable of colliding with
or being mistaken for a real GSIS id.

**FantasyPros DST market ranks** were being dropped at ingest, because identity resolved only
through `fantasypros_id`. They now join on the team code through an explicit three-entry alias
map (`JAC→JAX`, `LAR→LA`, `OAK→LV`); the other 29 codes already agreed. K was already on the
`ro` board. Both now enter around overall rank 150, which is where a 16-round 10-team draft
actually takes them — a useful independent check that the market data and the format line up.

### Both are baselines, and the weighting was measured

Walk-forward over real 2015–2025 seasons, every candidate compared against actual outcomes:

| | n | year-over-year r | best | MAE | vs. prior-year |
|---|---|---|---|---|---|
| K | 368 | 0.406 | weighted 2-year (0.65/0.35) | **33.60** | 37.44 |
| DST | 352 | 0.294 | 0.3·prior + 0.7·positional mean | **22.55** | 27.14 |

The right answer differs by position, which is why this is not one formula applied to both: a
kicker's own history carries real signal and two seasons beat one; a defense's carries much
less, and shrinking hard toward the positional mean beats trusting the prior season by a wide
margin. Both signals are weak in absolute terms — that is a real property of these positions,
and an ML model here would imply an accuracy the data does not support.

## D58 — The target format is a 10-team 1-QB redraft league; capacity is flex-aware; the engine gains marginal starter value

**Format** (`docs/TARGET_FORMAT_1QB.md`): `QB1 / RB2 / WR2 / TE1 / FLEX2 / K1 / DEF1` = 10
starters, bench 6, `roster_size` 16. Supersedes D7's 2QB dynasty target, which stays registered
as `legacy_2qb_dynasty` — it is the format every pre-D56 result was measured under, and keeping
a genuinely different format exercised is what makes league-contextuality a property of the
code rather than a claim.

**Roster arithmetic was inconsistent and is now asserted.** The pre-D58 config declared 9
starters and a 10-player bench alongside `roster_size: 17` — three numbers that could not all
be true (`docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` §3). `roster_size` is also the benchmark's round
count, so an inconsistent one silently drafts the wrong number of players. A test now asserts
`starters + bench == roster_size` for every shipped config.

**Slot names are not position names.** A config (and Sleeper) calls the team-defense slot
`DEF`; nflverse and FantasyPros call the position `DST`. `dedicated_slots()` now normalizes
slot names into the data's position vocabulary, so the slot resolves to real rows instead of
silently going unfilled and scoring zero.

**Positional capacity is now flex-aware.** The old model split the bench evenly across
`dedicated_slots()` and ignored FLEX entirely. That was survivable with four positions and a
2-QB lineup; adding K and DEF took the divisor from 4 to 6 and made the error first-order —
capping RB at 3 in a league that starts 2 RB plus up to 2 FLEX, while handing kickers bench
room no roster uses. Capacity is now every slot a position could start in, plus a bench share
proportional to that, with a one-slot floor so a backup is never structurally forbidden:

| | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| old (even split) | 2 | 3 | 3 | 2 | 2 | 2 |
| new (flex-aware) | 2 | **6** | **6** | **4** | 2 | 2 |

`roster_need`'s depth target moves off the arbitrary `slots + 2` constant onto the same
league-derived figure. These are ceilings past which one more body cannot start, **not
targets**: the objective is realized starter points subject to feasibility, never a
roster-count goal.

**Marginal starter value.** The audit found the scoring path had no representation of the
team's own starting lineup: VORP measures against a *league-wide* replacement level and
`roster_need` measures a positional *count*, so a player was scored identically whether he
would be your WR1 or your WR5. `league/replacement.py::marginal_starter_value` asks instead
how much a candidate would improve this roster's best legal lineup — full projection into an
empty slot, zero at a saturated position, the margin over whoever he displaces otherwise.

Where that term belongs in the score is a measurement, not a preference. Tiers M0 (the shipped
formula, as control) through M3 (marginal starter value replacing VORP outright) vary only its
placement, with the decision rule pre-registered in source before any run against real data.

## D59 — Re-baselined benchmark: Alpha's shipped engine beats market consensus under the 1-QB board

Official benchmark (`alpha-squad evaluate draft-simulation`), full 2021–2025 × 10 slots, run
against the corrected `ro` board and corrected 1-QB league config from D56–D58, with the
scoring engine itself unchanged (this is D55's shipped opportunity-cost formula, scored on
the right board for the first time):

| Strategy | Mean starter pts | Mean total roster pts |
|---|---|---|
| `alpha_league_aware` | **1927.8** | 2785.4 |
| `market_consensus` | 1825.2 | 2806.7 |
| `generic_prior_year` | 591.5 | 3468.6 |
| `alpha_bpa` | 463.5 | 3612.0 |

**Alpha beats consensus by +102.6 mean starter points (+5.6%)** — the reverse of every
pre-D56 result, where consensus led by 219.6 points and Alpha never won a season. Win rate
at the (season, slot) level (not just the pooled mean): **34/50 (68%)**. Per-season: Alpha
wins 4 of 5 (2021/2022/2023/2025); loses 2024 (1797.8 vs 1877.9) — reported as a real result
rather than smoothed into the favorable pooled mean.

**The naive-baseline collapse is a real finding.** `alpha_bpa`/`generic_prior_year` — built
with deliberately zero VORP/roster awareness — fell to 463.5/591.5 starter points. Verified
against the actual drafted rosters (2024 slot 1): `alpha_bpa` drafted 15 QBs and 1 K;
`generic_prior_year` drafted 14 QBs and 2 WR. Zero RB/TE/DST in either. Not a simulator
defect: in a 1-QB format, raw point totals still favor QB, but nothing in either baseline's
logic knows only one team can start one — "take the highest points remaining" hoards QBs and
leaves 8 of 10 starting slots empty. Since `alpha_bpa` shares identical point predictions
with `alpha_league_aware` and differs only in whether VORP/roster-fit exists, the ~1464-point
gap between them is almost entirely that context's contribution.

This settles the directive's central benchmark question (is the 1-QB board appropriate, and
does Alpha beat it) but not why. Pick-level attribution and the M-tier ablation (measuring
whether marginal starter value improves further, and whether D55's opportunity-cost term
still helps specifically under this format) are the next diagnostic step — see
`docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §7–9.

## D60 — Marginal starter value ships to production, chosen by a pre-registered M-tier ablation

The M-tier ablation (`evaluation/draft_forensics.py`, D58) tested where marginal starter value
(`league/replacement.py::marginal_starter_value` — how much a candidate would improve *this*
roster's own best legal lineup, as opposed to VORP's league-wide replacement level) belongs in
the score, with the decision rule pre-registered before any run against real data: primary
metric mean starter points, Gate 1 no position zeroed out more than the control, Gate 2 no more
infeasible rosters than the control, tie-break fewer mechanisms, ship only if a tier strictly
beats the pre-registered control (M0, the shipped D55 formula unchanged) with both gates
passing. 200 real drafts (4 tiers × 5 seasons × 10 slots):

| Tier | Mean starter pts | Δ vs M0 | Win/Loss/Tie vs M0 |
|---|---|---|---|
| M0 (control — shipped D55 formula, unchanged) | 1894.2 | — | — |
| M1 (MSV added inside the value term) | 1987.2 | +93.0 (+4.9%) | 34/13/3 |
| M2 (MSV drives the roster-fit multiplier) | 1900.7 | +6.6 (+0.3%) | 16/22/12 |
| **M3 (MSV replaces VORP as the value base)** | **2003.8** | **+109.7 (+5.8%)** | **37/13/0** |

Both gates passed for every tier. **M3 wins outright** on the primary metric, by the largest
margin of any tier, winning 4 of 5 seasons head-to-head (loses only 2025, 4–6).

**M3 is also the only tier that fixes a real, independently-visible defect.** Every
VORP-value-base tier (M0/M1/M2) drafted a mean 3.7–3.8 kickers and 2.2–2.4 defenses per
16-round draft — 50/50 drafts in each of those tiers breached K's flex-aware feasibility cap —
because VORP prices a bench K/DST against league-wide positional replacement level with no
knowledge that neither position has flex eligibility: a second or third kicker merely better
than replacement still scores positive VORP despite having zero chance of ever starting. MSV
has no such blind spot by construction (a second kicker's MSV is exactly zero once the first
fills the slot). Only M3 stops the hoarding (0/50 breaches) and the freed bench capacity flows
to real skill-position depth (mean RB 1.72→2.62, WR 4.12→5.54, TE 2.00→2.70).

**Shipped exactly as measured.** `recommend_draft_pick` gains an optional `roster_player_ids`
parameter. When a caller supplies the roster's actual drafted players, the score's value base
becomes marginal starter value instead of VORP; when omitted, the function is byte-for-byte the
D55 formula, so every caller that cannot supply real player ids (some API/agent paths — the web
draft picker's `draftedIds` tracks every player drafted league-wide, not this team's own picks,
so passing it would tell the engine "my roster already holds every position anyone has drafted,"
which is actively wrong rather than merely incomplete; the CLI and `agents/registry.py` only
ever resolve position counts, not player ids) sees no behavior change. VORP is still computed
unconditionally, since the D55 opportunity-cost replay is itself VORP-denominated regardless of
which term is the score's value base. Wired into the official benchmark
(`draft_simulation.py`, which already tracks `drafted` as real player ids) and the forensic
harness's tier H, so it keeps mirroring real production.

**Official benchmark, re-run after shipping** (`alpha-squad evaluate draft-simulation`, full
2021–2025 × 10 slots, `ro` board, 1-QB league config):

| Strategy | Mean starter pts | Mean total roster pts |
|---|---|---|
| **alpha_league_aware (M3/D60)** | **1990.9** | 2455.0 |
| `market_consensus` | 1825.2 | 2806.7 |

**+165.7 mean starter points (+9.1%) over consensus, 37/50 (74%) win rate** — up from D59's
pre-MSV +102.6/+5.6%/68%. Byte-identical across two independent processes
(`md5 5e0ec53e...`, `PYTHONHASHSEED` unset), confirming the result is deterministic.

**Not settled by this change, named rather than hidden (full discussion:
`docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §7–9):** pick-level counterfactual attribution surfaced a
real RB-position projection residual (consensus RB alternatives in the "cost" bucket
overperformed their own projections by a mean +45.2 points, n=206, 2021–2025) that is a
projection-layer question, not a draft-engine one; D55's opportunity-cost term was held fixed
across every M-tier and was not independently re-ablated against an opportunity-cost-off
control under the 1-QB format specifically.

**SUPERSEDED BY D61.** The benchmark this entry reports against has a `market_consensus`
opponent that forfeits two of its ten starting slots. D60's shipping decision was correctly
reasoned on the evidence available at the time; the evidence itself was contaminated. The
mechanism change (MSV replacing VORP) is retained pending re-measurement, not endorsed.

## D61 — The 1-QB benchmark's consensus opponent forfeits two starting slots; D59/D60's margin is an artifact

Forensic re-examination of the shipped D60 engine (full analysis:
`docs/DRAFT_STRATEGY_FORENSIC_ANALYSIS.md`) found that the headline result — Alpha beating
market consensus by +165.7 starter points (+9.1%), 37/50 win rate — is produced by the
benchmark opponent rather than by Alpha's decisions.

**The mechanism.** `market_consensus` picks best-available by preseason overall ECR with no
roster awareness. On the real `ro`/`redraft-overall` board the best DST ranks **155th** overall
and the best K ranks **186th**. A 16-round 10-team draft is **160 picks**. So the consensus bot
drafts a mean of **0.00 kickers and 0.30 defenses** across 50 drafts and leaves its K and DEF
starting slots empty, scoring ~0 there. This is a real property of the FantasyPros overall
board — it ranks K/DST by overall value while every human applies a last-two-rounds positional
override — not a data defect. `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §2 and
`docs/EVALUATION_LIMITATIONS.md` both named the missing roster awareness as a limitation; what
was never quantified is that it exceeds the entire measured margin.

**Decomposing the 50 benchmark drafts by slot type:**

| | K + DEF slots | the 8 skill slots | total |
|---|---|---|---|
| `alpha_league_aware` | **275.1** | 1715.8 | 1990.9 |
| `market_consensus` | **29.8** | 1795.4 | 1825.2 |
| Alpha − consensus | **+245.3** | **−79.6** | +165.7 |

148% of the edge comes from two forfeited slots; on the eight skill slots Alpha is **behind by
79.6**.

**The fair comparison.** Re-simulating consensus with one change — fill K and DEF in the last
two rounds if still empty, best-available by ECR within the position, no hindsight:

| opponent | mean starter pts |
|---|---|
| consensus as-implemented | 1825.2 |
| consensus, roster-aware | **2039.2** (+214.0) |
| `alpha_league_aware` (shipped) | 1990.9 |

**Alpha vs a fair opponent: −48.3 mean starter points, win rate 25/50 (50%), 95% CI
[−122.2, +25.6] — the interval contains zero.** Per season: 2021 −25.9, 2022 +69.5,
2023 −145.3, 2024 −155.7, 2025 +15.9. The fair opponent's K+DEF slots score 270.2 against
Alpha's 275.1 — the advantage vanishes entirely, exactly as the mechanism predicts.

**Why Alpha trails on the skill slots.** D60 made `marginal_starter_value` the value base,
replacing VORP. On an empty roster MSV is mathematically identical to the candidate's own
projection, i.e. pure best-player-available by raw points — and in a 1-QB league raw points
favour quarterbacks, which is precisely what VORP existed to correct. Measured top-5 by each
value base: MSV yields 4–5 QBs in 2021/2023/2025; VORP yields **zero** in all three. The
behavioural consequence in real drafts: Alpha takes a QB in round 2 in **68%** of drafts, takes
WR almost exclusively through round 5, reaches its first RB at mean round **5.24** (consensus:
2.72), and finishes with **2.74** RBs (consensus: 5.12). This is the same pathology that
collapses `alpha_bpa` to 463.5, mitigated only by the bounded roster-fit multiplier.

MSV's benefit was real and is retained as a finding: it fixed genuine K/DST *hoarding*
(M0 drafted 3.78 K and 2.26 DST per draft, breaching the cap in 50/50 drafts; M3 drafts
1.60/1.26, breaching 0/50). It over-corrected on *timing* — Alpha now takes DST in round 10 in
**100%** of drafts and K at median round 9, against a measured cost of waiting of only 20–50
realized points. The `opportunity_cost` term cannot counteract this because it is
VORP-denominated while the value base is MSV: a scale mismatch introduced by D60.

**Two measurement defects found in the same pass.**
1. `evaluation/draft_forensics.py::_feasibility_cap` is the pre-D58 flex-blind formula while
   production calls the D58 flex-aware `positional_feasibility_cap`. Measured caps diverge:
   RB 3 vs 6, WR 3 vs 6, TE 2 vs 4. So tier M0, documented as "the shipped production formula,
   unchanged — the control", is not, and M3's winning WR count of 5.54 exceeded the harness cap
   it was measured under. This also explains the previously unreconciled gap between harness
   numbers (M0 1894.2, M3 2003.8) and official-benchmark numbers (1927.8, 1990.9).
2. `evaluation/pick_attribution.py` never passed `roster_player_ids`, so the 800-pick
   attribution in `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` §7 measured the D55 VORP engine, not
   the shipped D60 MSV engine. The RB-residual finding must be re-derived before being cited
   about the shipped engine.

**Also corrected:** D60 and the diagnostic reported `alpha_league_aware` mean total roster
points as 2775.9; the real value in `reports/draft_simulation.md` is **2455.0**. The starter
figure (1990.9) was correct. The genuine 2785.4 → 2455.0 drop from D59 to D60 is itself a
finding — MSV concentrates value into starters and gives up bench depth.

**Decision.** No engine change is made on this evidence. The measurement is fixed first: the
benchmark opponent becomes roster-aware (derived from `dedicated_slots()`, never hardcoded),
both opponents are reported side by side so no published number is silently restated, the
forensic cap is reconciled with production, and attribution is pointed at the shipped engine.
Only then is a value-base ablation run — testing formulations that retain **both** league-wide
scarcity and lineup saturation rather than trading one for the other. Sequencing, candidate
tiers, the pre-registered decision rule (now including a per-season consistency gate and a
positional-timing gate that would have caught this regression), and the explicit
do-not-pursue list are in `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`.

`docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0 is **reopened**: its acceptance criterion was
declared met against the contaminated benchmark.

**What still stands from D56–D60, re-verified in this pass:** the market-series correction
(D56), the computed K/DST scoring and measured baselines (D57), the 1-QB format retarget and
flex-aware capacity (D58). None of the findings above impugn them. Also genuinely real and
worth preserving: Alpha's consistency advantage — starter-points stdev **158.9** vs consensus's
**214.5**, and a higher floor (worst draft 1570.3 vs 1392.7).

## D62 — Stage 1 measurement fixes land; D61's fair-opponent estimate confirmed by direct re-run

`docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md` Stage 1 (measurement only, no engine change) is
implemented and the official benchmark re-run against real 2021–2025 data. This section records
what shipped and the true current baseline; it supersedes D61's *simulated* fair-opponent
estimate with a *measured* one from the actual shipped code.

**What shipped, all in this pass:**
1. **Roster-aware consensus opponent** (`evaluation/draft_simulation.py`). A new
   `market_consensus_roster_aware` strategy/opponent: once a drafter has exactly as many picks
   left as still-unfilled mandatory dedicated slots (`league/roster.py::unfilled_dedicated_slots`,
   new — derived from `dedicated_slots()`, never hardcoded), it is restricted to filling one,
   still best-available by ECR within that pool. `market_consensus` is kept byte-identical so
   every number published through D60 stays reproducible under its original label (the D56
   precedent). `simulate_draft`/`run_draft_simulation` gain an `opponent_strategy`/
   `opponent_strategies` parameter; `draft_simulation_results` gains `opponent_strategy` (now
   part of the persistence key) and `n_unfilled_mandatory_slots` columns, with a migration for
   pre-D61 databases (`storage/db.py::_migrate` — caught by running the CLI against the real
   local database, not just fresh in-memory test fixtures; see the migration commit for why the
   table is dropped rather than carried forward: it is a pure evaluation-result cache, and
   inventing an `n_unfilled_mandatory_slots` value for rows that predate the column would
   fabricate data no version of the code ever measured).
2. **Feasibility cap reconciled.** `evaluation/draft_forensics.py`'s pre-D58 flex-blind
   `_feasibility_cap` is deleted; the harness now calls production's
   `league/roster.py::positional_feasibility_cap` directly, with a test asserting no
   forensic-local copy can reappear.
3. **Attribution measures the shipped engine.** `pick_attribution.py` now passes
   `roster_player_ids=my_roster` to `recommend_draft_pick`, activating D60 marginal starter
   value instead of silently falling back to D55 VORP.
4. **Unfilled slots are reported, not silently zeroed.** `write_draft_simulation_report` shows
   both opponent fields side by side with a banner naming the headline claim, plus mean/count of
   unfilled mandatory slots per strategy.
5. **`next_pick_survival_probability` scoped by `page_type`** (`league/draft.py`), closing the
   last market consumer that filtered on `ecr_type` alone.

**The re-run, against real 2021–2025 data, 10 slots, both opponent fields (500 total simulated
drafts):**

| opponent field | strategy | mean starter pts | stdev | unfilled slots |
|---|---|---|---|---|
| `market_consensus_roster_aware` | `market_consensus_roster_aware` | 2034.8 | 202.7 | 0.00 |
| `market_consensus_roster_aware` | `alpha_league_aware` | 1989.3 | 160.8 | 0.00 |
| `market_consensus` (as published through D60) | `market_consensus` | 1825.2 | 214.5 | 1.88 |
| `market_consensus` (as published through D60) | `alpha_league_aware` | 1990.9 | 158.9 | 0.00 |

**Alpha vs the fair opponent, measured (not simulated): −45.4 mean starter points, win rate
25/50 (50%), 95% CI [−117.1, +26.2] — the interval contains zero.** Per season: 2021 −30.5,
2022 +99.0, 2023 −125.9, 2024 −160.3, 2025 −9.4. This confirms D61's simulated estimate
(−48.3, 25/50) to within 3 points and the same sign pattern per season — the two independent
computations (D61's targeted re-simulation vs this pass's full shipped-code re-run) agree, which
is itself evidence the mechanism is understood correctly rather than an artifact of either
measurement's specific implementation.

**Determinism.** The new roster-aware opponent path was run twice as separate `uv run python3`
processes (`PYTHONHASHSEED` unset) against 2021 data, both opponent fields,
`market_consensus_roster_aware` and `alpha_league_aware` strategies: byte-identical JSON output,
confirming the fix introduced no new non-determinism (`available`/`unfilled_dedicated_slots`
build ordinary Python sets/dicts, but the final selection is still resolved through
`best_by_market_rank`'s existing `(rank, player_id)` tie-break).

**Status.** `docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0 stays **reopened**: Alpha does not beat a
fair consensus opponent (−45.4, 95% CI includes zero). Stage 1 is closed; Stage 2 (re-run the
M-tier ablation honestly under the fair opponent and production's real caps) and Stage 3 (the
pre-registered N0–N4 value-base ablation) remain, per
`docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`, not started in this pass.

## D63 — The draft value base becomes `msv + VORP`, chosen by a pre-registered N-tier ablation

Stages 2 and 3 of `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`. The pre-registered decision rule
was committed to `evaluation/draft_forensics.py` (commit `622c468`) **before any N-tier was
run**, per the D39/D54/D55 discipline and the plan's explicit instruction.

### A measurement defect found first (Stage 2)

`evaluation/draft_forensics.py` still ran its 9-slot opponent field on the pre-D61 *unaware*
consensus. An M-tier re-run would therefore have re-measured the very artifact D61 identified.
Fixed before measuring anything: `simulate_forensic_draft`/`run_tier_ablation` take an
`opponent_strategy`, and it is recorded on every result row so a tier figure can never be read
without knowing which opponent produced it.

**Harness validation.** With the Stage 1.2 cap fix and the fair opponent in place, the forensic
harness reproduces the official benchmark **exactly** for the shipped formula — max|difference|
= 0.000000 over 50 paired drafts. Forensic tier numbers are therefore directly comparable to
benchmark numbers, which is what makes the rest of this entry load-bearing rather than merely
indicative.

### Stage 2 — does MSV actually beat VORP once undistorted?

M-tiers, 2021–2025 × 10 slots, against both opponent fields:

| tier | value base | vs unaware opponent | vs FAIR opponent |
|---|---|---|---|
| M1 | vorp + msv | 2028.8 | **2029.2** |
| M3 | msv (shipped D60) | 1990.9 | 1989.3 |
| M0 | vorp (D55) | 1927.8 | 1926.8 |
| M2 | msv as a bounded multiplier | 1929.0 | 1924.4 |

**Yes** — MSV beats VORP by +62.6 against the fair opponent, essentially unchanged from +63.1
against the unaware one. The opponent artifact invalidated D59/D60's *claim of beating
consensus*; it did not distort the internal M-tier ranking.

**But D60 still selected the wrong tier.** M1 now leads M3 by +39.9; the pre-D63 harness had M3
ahead (2003.8 vs 1987.2). The cause is the Stage 1.2 cap reconciliation, not the opponent: the
old forensic `_feasibility_cap` capped RB/WR at 3 where production allows 6. The opponent is
ruled out directly — M3 − M0 is +63.1 unaware and +62.6 fair, and M3's QB-by-round-2 rate is
92% under *both* fields. (D61 recorded 68% for that rate under the pre-Stage-1.2 caps; the
conditions differ, so the figures are not comparable and 92% is the post-fix number.)

### Stage 3 — the value-base ablation

Ten variants × 10 slots × 5 seasons = 500 real drafts, fair opponent, production's real caps.
Every tier runs the *same* code path with the same risk/survival/roster-fit/feasibility terms;
only the value base varies, so a difference is attributable to it and nothing else.

| tier | value base | starter pts | stdev | margin vs N0 |
|---|---|---|---|---|
| N4x | msv + 1.0·vorp, no opp-cost | 2032.8 | 139.9 | +43.4 |
| **N4** | **msv + 1.0·vorp** | **2029.2** | **131.7** | **+39.9** |
| N0 | msv (shipped D60) — *control* | 1989.3 | 160.8 | — |
| N0x | msv, no opp-cost | 1975.6 | 167.8 | −13.7 |
| N2 | min(vorp, msv) | 1942.4 | 146.4 | −46.9 |
| N3 | msv over replacement | 1940.7 | 149.9 | −48.6 |
| N1 | vorp (D55) | 1926.8 | 164.7 | −62.6 |
| N2x / N3x / N1x | the same, no opp-cost | 1867.1 / 1859.8 / 1832.8 | | −122 / −130 / −157 |

**The decisive result: summing the two signals wins; choosing between them per-candidate
loses.** Both clamping formulations were front-runners in the plan and both finished *below*
the control. N3 was predicted to be "most likely to be right" — it reduces to VORP on an empty
roster and to 0 at a saturated position, verified by construction — and it lost by 48.6. The
hypothesis was right that the two bases fail in opposite regimes; it was wrong that the fix is
to select between them pointwise.

**N4 vs the control, paired:** +39.9, 95% CI [+9.1, +70.6], winning **37 of 50** drafts. All
four pre-registered gates pass, and the margin survives leave-one-season-out on every season
(+48.2 / +39.1 / +27.2 / +50.2 / +34.7).

### The opportunity-cost term is kept, re-measured rather than assumed

D60 left open a scale mismatch: the term is VORP-denominated and was added to an MSV base. Each
base was therefore run with it on and off:

| value base | effect of the opportunity-cost term |
|---|---|
| vorp (N1) | **+94.0**, CI [+64.2, +123.7] |
| msv over replacement (N3) | **+81.0**, CI [+51.8, +110.2] |
| min (N2) | **+75.3**, CI [+48.7, +102.0] |
| msv (N0) | +13.7, CI [−12.4, +39.9] — not significant |
| msv + vorp (N4) | −3.6, CI [−22.3, +15.2] — not significant |

It is significantly *helpful* on three of five bases and indistinguishable on the winner. D55's
finding stands. **Kept.**

**A judgment call, recorded as one.** N4x (opportunity cost off) scored +3.6 above N4, and the
pre-registered tie-break's first criterion is "fewer mechanisms", which favours N4x. N4 ships
anyway, for reasons stated so the call is reviewable and reversible (`DRAFT_VORP_WEIGHT` and
the tier spec are one-line changes): the +3.6 is not statistically distinguishable (CI contains
zero, 14W/13L); N4 has the lower variance, which is the tie-break's *second* criterion; N4
breaches the kicker cap in 32 of 50 drafts against N4x's 40; and removing a term that helps
significantly on three other bases would make the engine brittle to any future value-base
change — it is what protects against the positional-depletion pathology M17/M18 diagnosed.

### Official benchmark, after shipping

`reports/draft_simulation.md`, real 2021–2025, fair opponent. The forensic harness predicted
2029.2 and production delivered **2029.2** — exact agreement.

| | before (D62, msv) | after (D63, msv + vorp) |
|---|---|---|
| Alpha mean starter pts | 1989.3 | **2029.2** |
| fair consensus | 2034.8 | 2034.8 |
| margin | −45.4 | **−5.6** |
| 95% CI | [−117.1, +26.2] | [−68.4, +57.2] |
| win rate | 25/50 | 25/50 |

**88% of the gap to a fair consensus opponent is closed.** Alpha still does not beat it: the
margin is negative, the win rate is 25/50, and the interval contains zero. Per season: 2021
−23.9, 2022 +141.8, 2023 −35.3, 2024 −161.7, 2025 +51.3. `IMPLEMENTATION_GAP_ANALYSIS.md`
P1-0 stays **open**.

Genuinely improved alongside the mean: the floor. Worst draft rises 1570.3 → 1765.3 and
starter-points stdev falls 160.8 → 131.7, so the consistency advantage D61 identified as real
is extended rather than spent.

**Determinism verified.** The new value base was run twice as separate `uv run python3`
processes (`PYTHONHASHSEED` unset), 2021, both opponent fields, `alpha_league_aware`:
byte-identical JSON (md5 `51fa3dd4…` both runs). Summing two float terms introduced no new
ordering sensitivity — the score's tie-break is still `(-score, player_id)`.

### Known regression, reported rather than buried

The blend trades one hoarding mode for another. MSV-dominant bases over-draft quarterbacks;
VORP-containing bases over-draft kickers, because VORP prices a bench K above replacement with
no knowledge that the position has no flex eligibility — the exact blind spot D60 set out to
fix.

| tier | drafts breaching a positional cap (of 50) | mean K | mean QB |
|---|---|---|---|
| N0 (was shipped) | QB 25, WR 8 | 1.60 | 2.28 |
| N4 (now shipped) | **K 32**, WR 2 | **2.74** (cap 2) | 1.60 |

**No pre-registered gate catches over-drafting** — Gate 1 checks zeroing, Gate 2 infeasibility,
Gate 4 timing. N4 passed the rule legitimately and still carries this defect. It is net
positive on the objective (starter points rise, and a wasted late-round kicker is cheap), but
it is a real defect and the leading next-phase item: the plausible fix is to apply lineup
saturation to the VORP term as well, or to tighten `OVER_CAP_VALUE_MULTIPLIER`, measured the
same way. Positional timing otherwise improved or held: QB-by-round-2 92% → 66%, first DST
round 10.0 → 9.6, first K 8.5 → 8.0; first RB drifted slightly later, 5.24 → 5.50.

### What did not change

The projection model. The forensic work established the player model is not the bottleneck, and
nothing here contradicts that: every tier used identical projections and the spread between
best and worst was 200 starter points, produced entirely by the decision layer.

## D64 — N4's kicker hoarding: both hypotheses measured, neither ships; N4 is kept

D63 shipped `msv + VORP` and recorded a known regression: the blend breaches the kicker cap in
32 of 50 drafts (mean 2.74 K against a cap of 2), which no pre-registered gate checked. This
entry is the follow-up experiment. **Outcome: no candidate ships. The production value base is
unchanged.** `league/draft.py` is byte-identical to its D63 state.

### The mechanism, traced rather than assumed

D63 attributed the hoarding to "VORP prices a bench K above replacement with no knowledge that
the position has no flex eligibility." Replaying a real hoarding draft (2023, slot 9 — kickers
at rounds 8, 11 and 16) pick-by-pick through the production scoring path shows that is only
partly right, and the missing part is what defeats one of the two proposed fixes.

At round 11, the pick that actually matters, the top candidates were:

| candidate | MSV | VORP | fit | over-cap | score |
|---|---|---|---|---|---|
| **K (taken)** | 0.0 | **+30.1** | 1.00 | **not applied** | **21.04** |
| DST | 0.0 | +10.2 | 1.00 | not applied | 7.14 |
| TE | 0.0 | +4.8 | 1.00 | not applied | 4.08 |
| RB | 0.0 | +2.0 | 1.00 | not applied | 1.12 |

The real chain is:

1. By the late rounds every startable slot is full, so **MSV is 0.0 for every candidate** and
   the value base collapses to VORP alone.
2. VORP is measured against a **static, league-wide preseason replacement level**. Ten teams
   strip the skill pools, so the best available skill player falls far *below* replacement
   (measured at round 16: RB −135.6, WR −123.0, TE −126.9, QB −273.5). Almost nobody drafts
   kickers, so the best available K is still far *above* it (+30.1 at round 11, +17.2 at 16).
3. VORP therefore favours K/DST late. **Flex eligibility is the second-order cause, not the
   first**: it is why K saturates at one startable slot while RB/WR have four.

Two consequences followed directly, and both were confirmed by measurement:

- **The second kicker is taken while still UNDER the feasibility cap** (1 < 2). At that pick
  *all* of the top 20 candidates are under-cap, so the over-cap multiplier is not even engaged.
- At the third kicker every alternative is at or below replacement, so no *positive* multiplier
  can reorder a positive kicker above a non-positive skill player. The probe reported the
  multiplier "would need to be < −0.0000 to flip".

**Hypothesis B was therefore predicted inert before it was run.** It was run anyway.

### Variants (control R0 = the shipped D63 engine; R0 reproduces it exactly)

Pre-registered in source before any run: control R0, primary metric mean starter points vs. the
fair opponent, Gates 1–4 reused verbatim from D63, plus a **new Gate 5** — cap breaches must not
increase at any position, the gap that let D63's regression through. Explicitly *not* a goal:
fewer kickers.

| tier | mechanism | starter pts | margin | 95% CI | W/L | QB/RB/WR/TE/K/DST | breaches |
|---|---|---|---|---|---|---|---|
| **R0** | shipped `msv + VORP` — control | **2029.2** | — | — | — | 1.60/2.20/5.42/2.06/**2.74**/1.98 | K 32, WR 2 |
| R2 | Hyp B: over-cap 0.1 → 0.01 | 2029.2 | **+0.0** | [+0.0, +0.0] | 0/0 | 1.60/2.20/5.62/2.06/2.54/1.98 | K 22, WR 2 |
| R1 | Hyp A: saturate the VORP surplus | 1996.3 | **−32.9** | [−62.2, −3.6] | 18/28 | **2.60**/2.86/5.12/3.16/1.20/1.06 | **QB 14**, WR 1 |
| R3 | Hyp A + B | 1996.3 | −32.9 | [−62.2, −3.6] | 18/28 | identical to R1 | QB 14, WR 1 |
| R4 | Hyp A, zero-tie defect repaired | 2030.5 | **+1.3** | [−32.0, +34.6] | 19/27 | 1.62/**4.00**/5.02/3.18/**1.12**/1.06 | QB 4 |

**Hypothesis A** scales a candidate's value *above* replacement by the fraction of his
position's startable capacity still unfilled (`league/roster.py::startable_saturation` and
`saturated_surplus`), leaving value *below* replacement untouched — the same `max(0, …)` clamp
and the same reasoning `positional_opportunity_cost` already documents. Nothing is hardcoded per
position: K keeps none of its surplus after one kicker because K has **1** startable slot, while
a third RB keeps a quarter because RB has **4** (2 dedicated + 2 FLEX). The distinction emerges
from the lineup config, as required.

### Did either hypothesis help?

**Hypothesis B: no — and it cannot.** R2's margin is exactly **+0.0**, with a 0/0 win/loss
record: not one of the 50 drafts changed its starter points. It *does* change picks (K breaches
32 → 22, total roster points 2670.4 → 2678.3), but only picks made when the roster is already
over cap — i.e. bench bodies that can never start. Rescaling a set of candidates that all
receive the same factor cannot reorder them, which is now asserted by test.

**Hypothesis A: no, as implemented.** R1 loses **32.9** starter points (CI excludes zero,
losing 28 of 50 drafts). It fixes kickers decisively (2.74 → 1.20) and then **creates a
quarterback pathology in their place** (QB 1.60 → 2.60, QB cap breached in 14 of 50 drafts
against the control's 0) — the "shifting the symptom elsewhere" failure the phase was warned
about. Gate 3 fails (worse in 4 of 5 seasons) and leave-one-season-out fails on all five.

**A diagnosed defect in R1, repaired as R4 (post-hoc, labelled as such).** Zeroing a saturated
position's surplus collapses many late candidates to a score of *exactly* 0.0, and the generic
`(-score, player_id)` sort then resolves those ties **alphabetically**. Measured over 144 real
picks, R1 decides **19% of its picks that way** against R0's 0% — one pick in five effectively
random. R4 changes only the tie-break, preferring the candidate with the most startable capacity
remaining (justified because the benchmark scores the best legal lineup from *realized* points,
so a bench WR who outperforms can still enter the lineup while a third kicker never can).

R4 is the most interesting result and still does not ship. It produces by far the best roster
structure — total cap breaches **34 → 4**, K 2.74 → 1.12, RB 2.20 → 4.00, TE 2.06 → 3.18 — for a
starter-point margin of **+1.3, 95% CI [−32.0, +34.6]**. That is noise, and the shape of the
noise is exactly what the gates exist to catch: R4 **loses 27 of 50 drafts** while its positive
mean is carried by a handful of large outliers (+227.3, +193.4, +176.6). Per-slot means swing
from +69.1 (slot 10) to −65.1 (slot 8). Gate 3 fails (worse in 3 of 5 seasons), LOSO fails, and
Gate 5 fails (QB breaches 4 vs the control's 0).

### Against the actual objective

| candidate | vs fair consensus | 95% CI | win rate |
|---|---|---|---|
| R0 (= N4, shipped) | **−5.6** | [−68.4, +57.2] | 25/50 |
| R2 | −5.6 | [−68.4, +57.2] | 25/50 |
| R4 | −4.3 | [−67.5, +58.9] | 25/50 |
| R1 | −38.4 | [−102.6, +25.7] | 21/50 |

**Alpha still does not beat fair consensus under any candidate.** `IMPLEMENTATION_GAP_ANALYSIS.md`
P1-0 stays **open**.

### Decision

**Keep N4.** Under the decision hierarchy — starter points, then robustness, then win rate, then
roster feasibility — the only candidate that ties on starter points (R4, +1.3 ns) is decisively
*worse* on robustness, which outranks the roster-feasibility axis where it excels. Shipping a
change that loses 27 of 50 drafts and fails two robustness gates, to buy roster shape the
objective does not reward, would be optimising for rosters that look sensible. The phase's own
rule forbids exactly that: reducing kicker count was evidence, never the goal.

### What this establishes for the next phase

The kicker hoarding is **not** primarily a flex-eligibility bug, so no amount of
capacity-shaping on the value base fixes it cheaply. It is a **stale-replacement-level** bug:
VORP compares against a preseason league-wide pool that no longer resembles the board once ~150
players are gone. The highest-value next step is therefore a **draft-aware replacement level**
— recompute each position's replacement against the *currently available* pool rather than the
preseason one — which would deflate the kicker's phantom surplus and inflate the genuinely
scarce skill positions *without* touching the value base or its saturation. That is a
substantive change to `league/replacement.py` and belongs in its own pre-registered phase.

Retained regardless of the outcome: `startable_saturation`/`saturated_surplus` stay in
`league/roster.py` with tests, unused by production. They are correct, measured, and the natural
building blocks for the next attempt.

## D65 — Static replacement level is a real causal defect; draft-aware replacement is promising but not yet shippable

Forensic study, **no production change**. `league/draft.py` is byte-identical to its D63 state.
This entry answers the question D64 left open: is the stale, static replacement level actually
causing N4's late-draft behaviour, and what is the principled way to make it draft-aware?

**Verdict: hypothesis SUPPORTED on mechanism, and the correction produces the first measured
result that beats fair consensus — but it fails a pre-registered robustness gate, so it does
not ship in this phase.**

### Phase 1 — how replacement level actually works (traced in code, not assumed)

| question | answer |
|---|---|
| How is it calculated? | `league/replacement.py::replacement_level` → `compute_league_starters`: fill `teams × dedicated` slots by within-position rank, then flex slots by best-remaining across eligible positions; replacement = projection of the **best non-starter** at that position |
| What pool? | `load_season_projections(con, season)` — the **entire preseason universe** |
| Based on what? | Full preseason pool + league starter demand + real flex allocation. No bench component |
| Position-specific? | Yes |
| Once per season or dynamic? | Recomputed **every pick**, but always from the identical full pool, so it is **numerically constant across the draft**. Confirmed structurally: `available_player_ids` never reaches the VORP calculation (`draft.py:198` vs its only uses at 214/217/235) |
| Includes K/DEF? | Yes |

**The measured staleness (2022, round 13, real data).** Static level vs. the level implied by
the players actually still on the board:

| position | static | available-pool | error |
|---|---|---|---|
| QB | 289.2 | 111.0 | **+178.2** |
| WR | 149.0 | 79.9 | **+69.1** |
| RB | 146.7 | 84.4 | +62.3 |
| TE | 133.7 | 88.1 | +45.6 |
| **K** | 132.2 | 130.0 | **+2.2** |
| **DST** | 98.7 | 92.4 | +6.3 |

So the engine is **not over-valuing kickers — it is under-valuing everyone else.** Ten teams
strip the skill pools while barely touching K/DST, so the static level stays almost exactly
right for kickers and becomes wildly wrong for skill positions. A late WR is scored against a
replacement level 69 points too high, crushing its VORP toward zero.

**MSV's role, measured across four traced drafts** (2021 slot 1, 2025 slot 1, the best N4 draft
2022 slot 8, and the worst K-hoarder 2022 slot 4): MSV hits exactly 0.0 at **round 11 in all
four**, and stays there. From that point the value base *is* VORP, so the stale level governs
the last 6 of 16 rounds — which carry **16.1% of realized starter points** (327.4 of 2029.2),
with 36% of those picks entering the realized lineup.

### The premise of D64's kicker concern was itself wrong

Before testing fixes, the target was quantified by a drop-one counterfactual on real rosters:

| | value of that kicker | changed the lineup |
|---|---|---|
| 2nd kicker | **+27.4** starter pts | 17/18 drafts |
| 3rd kicker | **0.0** | **0/27** |
| 4th kicker | **0.0** | **0/5** |

The 2nd kicker is genuinely valuable — the benchmark scores the best legal lineup from
*realized* points, so holding two kickers is a max-of-2 draw on a high-variance slot. The 3rd
and 4th are worth **exactly nothing** and never start. Since a marginal late skill pick is worth
+7.3, perfectly reallocating those wasted picks is worth about **+4.7 starter points** — far
inside the ±33 confidence half-width. **A kicker-driven win was never detectable**, which
explains D64's R4 (+1.3) precisely. This ceiling was recorded in source *before* the variants
ran, so the result could not be reinterpreted afterwards.

### Phase 2 — three draft-aware definitions (`evaluation/replacement_diagnostics.py`)

Diagnostic-only, asserted by test to stay out of production. No tuned constants.

- **Candidate A — available-pool.** Run the *existing, unmodified* VBD allocation over only the
  players still on the board. Changes the pool and nothing else.
- **Candidate B — remaining-demand.** `remaining_demand[pos] = max(0, teams × startable_slots[pos] − drafted[pos])`;
  replacement = the `remaining_demand`-th best available player. Demand comes from the lineup:
  the league needs 10 kickers total but 40 WRs.
- **Candidate C — hybrid.** As B, with demand from the existing `positional_capacity`
  (startable + proportional bench share, the same function `positional_feasibility_cap` uses).

### Phase 3 — results (control V0 = shipped N4; V0 reproduces it exactly)

| tier | starter | margin vs N4 | 95% CI | W/L | vs fair consensus | QB/RB/WR/TE/K/DST | cap breaches |
|---|---|---|---|---|---|---|---|
| **VC** (hybrid) | **2052.4** | **+23.2** | **[+2.3, +44.1]** | 30/20 | **+17.6** | 1.48/3.06/4.74/4.00/1.72/1.00 | **0** |
| VA (available-pool) | 2042.6 | +13.4 | [−6.4, +33.2] | 32/18 | +7.8 | 2.00/2.88/5.76/3.36/1.00/1.00 | **0** |
| V0 (= N4) | 2029.2 | — | — | — | −5.6 | 1.60/2.20/5.42/2.06/2.74/1.98 | 34 |
| VB (starters-only demand) | 2017.9 | −11.3 | [−43.3, +20.6] | 21/29 | −16.9 | 1.06/2.00/3.74/5.36/2.00/1.84 | 47 (TE) |

**VC's margin over N4 is statistically significant** (CI excludes zero) and **survives
leave-one-season-out on all five seasons** (+28.5 / +32.5 / +2.3 / +38.0 / +14.7). It eliminates
*every* cap breach (34 → 0), lowers positional concentration (0.339 → 0.301), and is the first
configuration ever measured that **beats fair consensus (+17.6)** — though that interval still
contains zero.

**VB is rejected outright**: forcing demand to starters-only makes TE look permanently scarce,
producing 5.36 TEs and 47/50 TE cap breaches — the mechanism turned too blunt.

### Phase 4 — stress tests, including one that materially weakens the case

- **The gain is NOT the kicker fix.** Splitting the 50 drafts: where VC drafted *the same*
  number of kickers as the control it still gained **+13.3** (n=8); where it drafted fewer,
  +25.1 (n=42). Consistent with the pre-registered +4.7 kicker ceiling — most of the benefit is
  skill re-ranking, exactly as the mechanism predicts.
- **The late-round regime genuinely changes.** Rounds 11–16 composition moves from
  K 1.74 / DST 0.98 / RB 0.22 to K 0.72 / DST 0.38 / RB 1.06 / TE 2.82. Skill positions become
  competitive again.
- **Per-slot:** VC is worse on average in only 2 of 10 draft slots.
- **Per-season — the real weakness.** VC is worse in **2 of 5 seasons**, and in 2024 it loses
  **0/10 drafts** (−36.1). Against that, 2023 is +106.9 (9/10) and 2025 is +57.4 (10/10).
  **Gate 3 (at most 1 worse season) therefore FAILS**, for both VC and VA.
- **Diagnosed cause of the season dependence:** VC loads TE to exactly its capacity of 4.0 in
  *every* season (up from ~2.06). The 2024 pools are not structurally unusual, so this is a
  systematic strategy shift whose payoff is genuinely season-dependent, not a data artifact.
  Five seasons cannot distinguish a real edge from TE-outcome variance here.

Determinism verified for all four V-tiers across repeated runs.

### Decision

**Hypothesis supported; nothing shipped.** Under the pre-registered rule VC does not ship
(Gate 3 fails), and this phase was scoped as forensic regardless. N4 remains production.

That said, VC is the **strongest candidate this project has produced**: significant paired
margin, LOSO-robust, zero cap breaches, better concentration, and the first positive number
against fair consensus. The blocker is concentrated and understood — a TE-loading behaviour
whose payoff varies by season.

### Recommended next step

A dedicated pre-registered phase for Candidate C, addressing exactly the Gate 3 failure:

1. **Investigate the TE loading.** VC hits the TE capacity of 4 in every season. Establish
   whether that is genuinely optimal or an artifact of `positional_capacity` giving TE a bench
   share that the remaining-demand formula then treats as real league-wide demand.
2. **Test a C-variant with the demand target between B's and C's** — e.g. startable slots plus
   *one* bench slot rather than the proportional share — measured, not assumed.
3. **Widen the evidence base if possible.** The blocker is a 5-season sample against a
   season-dependent effect. Additional seasons would do more than any further tuning.
4. Only then re-run the full gate set, and ship only on a clean pass.

Retained for that work, unused by production and covered by tests:
`evaluation/replacement_diagnostics.py` and the V-tiers.

## D66 — Candidate C's TE loading explained; demand DEPTH is the real parameter, and a variant passes every gate

Follow-up to D65, **no production change**. `league/draft.py` remains byte-identical to D63.
D65's C3 was blocked by a Gate 3 failure attributed to systematic TE loading. This entry finds
the cause, refutes the obvious fix, and identifies the mechanism that actually matters.

### Phase 1 — why C3 loads tight ends

`startable_slots` counts every FLEX slot **once per eligible position**. In the target format
the 2 FLEX slots are counted three times (RB, WR, TE), so it sums to **14 per team while the
lineup starts only 10**. The remaining-demand candidates inherit that error:

| target | per team | league-wide demand | real starting slots |
|---|---|---|---|
| `startable_slots` (C2) | 14 | 140 | 100 |
| `positional_capacity` (C3) | 22 | 220 | 100 |

TE absorbs the worst of it. Its startable count of 3 assumes it wins both flex slots — but
measured across **all five real seasons, WR wins all 20 league-wide flex slots and TE wins
zero**. True TE starter demand is **1.00 per team**; C3 demands 4. That 3–4× overstatement is
the loading mechanism.

### Phase 2/3 — the obvious fix is WRONG

Two repairs were pre-registered in git (`84b25ab`) before either ran: C4 `dedicated + 1 bench`
(14/team) and C5 `earned-starter demand` (read off the flex allocation
`compute_league_starters` already computes, summing to exactly the lineup size, 10/team).

| candidate | per-team demand | starter | vs N4 | 95% CI | W/L | vs consensus | seasons worse | breaches |
|---|---|---|---|---|---|---|---|---|
| C3 capacity | 22 | 2052.4 | +23.2 | [+2.3, +44.1] | 30/20 | +17.6 | 2/5 | 0 |
| C1 available-pool | — | 2042.6 | +13.4 | [−6.4, +33.2] | 32/18 | +7.8 | 2/5 | 0 |
| **C0 = N4 (control)** | static | **2029.2** | — | — | — | **−5.6** | — | 34 |
| C2 startable | 14 | 2017.9 | −11.3 | [−43.3, +20.6] | 21/29 | −16.9 | 3/5 | 47 |
| **C5 earned** | **10** | **1992.0** | **−37.2** | **[−53.0, −21.4]** | 7/36 | −42.8 | 4/5 | **60** |
| **C4 ded+1 bench** | **14** | **1976.8** | **−52.4** | **[−86.3, −18.5]** | 15/35 | −58.0 | 4/5 | 22 |

**Both repairs made things significantly worse, and C5 — the one that is arithmetically
"correct" — was the worst of all**, with the most cap breaches (60) and K back up to 4.32.

**Why.** A lower demand target draws the replacement level from a *shallower* index. Once
`remaining_demand` reaches 0 the replacement level becomes the *best available* player, so that
position's surplus is identically zero. Measured over 144 real picks: C5 hits demand exhaustion
in **17% of picks** and produces exact zero-score ties in 3%; C0 and C3 do so in **0%**. The
flex "over-count" was not functioning as an error — it was acting as a **depth buffer** that
keeps VORP discriminating late in the draft. This directly refutes this phase's own Phase 1
hypothesis, and is recorded as such.

### Phase 4 — demand depth is the real parameter, and the region is broad

Sweeping a uniform multiplier on `startable_slots` (the only thing that varies is *depth*):

| scale | league demand | can exhaust? | starter | vs N4 | 95% CI | seasons worse | breaches | TE | K |
|---|---|---|---|---|---|---|---|---|---|
| 0.75 | 106 | **yes** | 2025.8 | −3.4 | ns | 4/5 | 56 | 5.24 | 2.26 |
| 1.00 | 140 | **yes** | 2017.9 | −11.3 | ns | 3/5 | 47 | 5.36 | 2.00 |
| 1.50 | 210 | no | 2046.4 | +17.2 | ns | 3/5 | 0 | 4.00 | 1.40 |
| 2.00 | 280 | no | **2060.7** | **+31.5** | [+10.1, +52.9] | 2/5 | 0 | 3.98 | 1.08 |
| **2.50** | 350 | no | 2055.9 | **+26.7** | **[+7.1, +46.3]** | **1/5** | **0** | 3.90 | **1.00** |
| **3.00** | 420 | no | 2057.4 | **+28.2** | **[+6.4, +50.0]** | **1/5** | **0** | 3.50 | 1.28 |

**A broad plateau, not a spike** — every scale ≥ 1.5 beats N4 — and the plateau has a
*structural* explanation rather than a fitted one: a draft consumes 160 picks, so league-wide
demand must exceed 160 for exhaustion never to occur, i.e. **scale > 1.14**. The plateau begins
at exactly the first tested scale above that threshold.

**Two tiers pass every pre-registered gate**, with leave-one-season-out positive on all five:

| tier | margin | g1 | g2 | g3 | g4 | LOSO | **ships** |
|---|---|---|---|---|---|---|---|
| scale ×3.0 | +28.2 | ✓ | ✓ | ✓ | ✓ | ✓ (+24.5/+43.8/+23.5/+30.8/+18.1) | **yes** |
| scale ×2.5 | +26.7 | ✓ | ✓ | ✓ | ✓ | ✓ (+29.0/+38.3/+14.1/+31.7/+20.3) | **yes** |
| scale ×2.0 | +31.5 | ✓ | ✓ | ✗ | ✓ | ✓ | no |
| C3 capacity | +23.2 | ✓ | ✓ | ✗ | ✓ | ✓ | no |

### Out-of-format generalization — the strongest evidence here

The scale was chosen on 1-QB data. Re-run unchanged on the **`legacy_2qb_dynasty`** config
(different lineup, roster size 17, different consensus board), scale ×2.5 gains **+65.6 starter
points, 95% CI [+31.8, +99.5], W/L 34/16, significant** — while C3 manages only +23.6 (ns).
The mechanism transfers to a format it was never tuned on, which is genuine out-of-sample
support rather than a second look at the same five seasons.

### Mechanism

Late rounds (11–16) per draft, N4 → scale ×2.5: K **1.74 → 0.00**, DST 0.98 → 0.62,
RB 0.22 → 1.28, WR 1.46 → 1.22. Kicker hoarding disappears entirely and skill players stay
competitive late — without any positional rule. TE settles at 3.90 (cap 4, zero breaches) with
first-TE round essentially unchanged (5.6 → 5.8), so this is depth, not an earlier reach.

### Classification

| candidate | verdict |
|---|---|
| C4 dedicated+1 bench, C5 earned-starter, C2 startable | **Reject** — significantly worse; demand too shallow, exhausts, collapses VORP |
| C1 available-pool, C3 capacity | **Promising but not robust** — beat N4 but fail Gate 3 |
| **scale ×2.5 / ×3.0** | **Ready for implementation, with the caveat below** |

**The caveat, stated plainly.** The two passing scales were identified by looking at a 6-point
sweep, so "passes Gate 3" is a **post-hoc selection**, not a pre-registered win — ×2.0 has the
larger margin and fails the same gate, and ×2.0 vs ×2.5 is well inside noise. What is *not*
post-hoc is the mechanism: the plateau is broad, has a structural threshold, and reproduces in a
second league format. Production remains N4 and nothing is shipped on this evidence alone.

### Recommended next step

A short, strictly pre-registered confirmation phase:

1. **Pre-register the scale on the structural criterion, not the argmax** — the smallest depth
   that cannot exhaust with margin (league demand ≥ ~2× the 160 picks a draft consumes, i.e.
   scale 2.0–2.5) — committed to git *before* the confirming run.
2. Re-run the **official** `alpha-squad evaluate draft-simulation` benchmark end to end with
   that scale wired into production, plus determinism across two processes.
3. Ship only on a clean pass of the full gate set on that run.

Retained, unused by production and covered by tests: the C4/C5 definitions, the sweep factory,
and the V/VS tiers.

## D67 — Replacement depth has a structural answer: the demand a draft actually consumes. Shipped.

Follow-up to D65/D66, and the **first production change to `league/draft.py` since D63**. D66 left
`scale ×2.5`/`×3.0` passing every gate but selected post-hoc off a 6-point sweep, and recommended
pre-registering "≈2.0–2.5" as the structural criterion. That recommendation was wrong, and this
entry says why before saying what replaced it.

### Phase 1 — what the depth multiplier actually does

Deepening demand is arithmetically identical to **adding a fixed bonus to every player at a
position**, and the size of that bonus is set by the shape of that position's projection tail —
not by anything about scarcity. Start-of-draft replacement level and the resulting VORP bonus vs
production's static level, mean over real 2021–2025 data:

| variant | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| static (production) | 273.7 | 146.6 | 154.5 | 132.6 | 132.9 | 97.7 |
| ×1.5 | 230.6 | 65.8 | 108.2 | 43.5 | 123.8 | 94.2 |
| ×2.5 | 164.8 | 26.2 | 62.5 | 26.2 | 102.5 | 87.0 |
| ×3.0 | 122.1 | 12.7 | 47.3 | 14.8 | 75.1 | 80.2 |
| **VORP bonus at ×2.5** | **+108.9** | **+120.4** | **+92.0** | **+106.4** | **+30.4** | **+10.7** |

Kicker hoarding vanished at ×2.5 (D66: K 1.74 → 0.00 in late rounds) not because kickers were
priced correctly but because **everyone else received ~100 points and kickers received 30**. The
asymmetry comes from pool depth alone: ~225 WRs with a long tail, ~45 kickers whose tail collapses
to a 2.0 floor past rank ~35, and exactly 32 team defenses. A knob whose effect size is governed
by how many kickers exist in the database is a positional re-weighting in disguise, and **"×2.5"
was never a structural criterion**.

### Phase 1 — what a draft actually consumes, and why shape beats scale

Ten teams drafting the fair roster-aware consensus, 160 picks, per season 2021–2025:

| | QB | RB | WR | TE | K | DST | Σ |
|---|---|---|---|---|---|---|---|
| **consumed, per team** | **2.04** | **4.64** | **5.64** | **1.68** | **1.00** | **1.00** | **16** |
| `startable_slots` | 1 | 4 | 4 | 3 | 1 | 1 | 14 |
| `positional_capacity` | 2 | 6 | 6 | 4 | 2 | 2 | 22 |
| lineup slots | 1 | 2 | 2 | 1 | 1 | 1 | 10 |

`startable_slots` is wrong in **shape**, not merely in scale — it under-counts QB 2× and
over-counts TE 1.8×. No uniform multiplier can repair a shape error; it can only trade one
position's exhaustion against another's inflation.

### Phase 1 — where the calculation goes degenerate

Two degeneracies, audited over 800 real pick-states (160 picks × 5 seasons). **Exhaustion**
(`remaining_demand → 0`, replacement becomes best-available, the position's surplus is identically
zero) and **clamping** (`remaining_demand ≥ pool`, replacement drawn from players nobody will
draft). First round of exhaustion, `–` = never:

| target | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| ×1.0 `startable` | **8.8** | 12.6 | **9.4** | – | 16.0 | 16.0 |
| ×1.5 | 11.4 | – | – | – | – | – |
| ×2.0 | 15.4 | – | – | – | – | – |
| ×2.5 / ×3.0 | – | – | – | – | – | – |
| consumption | 15.4 | 14.4 | 15.6 | 14.6 | 16.0 | 16.0 |

**Clamping never occurred at any depth up to ×3.0**, at any position. Exhaustion is the only
binding constraint — and QB is what forced the uniform scale above 2.5, purely because its
`startable_slots` base is 1 in a format whose drafts take 2.04 QBs per team.

### Phase 1 — roster legality is not enforced anywhere in the engine

- `recommend_draft_pick` has **no hard constraint**; the only positional stops are soft
  (`roster_fit_multiplier`'s [0.7, 1.3], `OVER_CAP_VALUE_MULTIPLIER = 0.1`).
- `compute_league_starters(teams=1)` scores an unfilled slot as empty and worth 0 — no error.
- Proof it is permitted: **`alpha_bpa` finishes 50/50 drafts with a mean 6.48 unfilled mandatory
  starting slots**; `generic_prior_year` 5.60 in 50/50.
- The *fair opponent* has had this rule since D61; the engine never has.
- `alpha_league_aware`'s current 0.00 unfilled is bought **entirely by the static-replacement
  defect**, which prices a kicker at +30 to +50 VORP all draft. Today's legality is a side effect
  of the bug being removed.

**Platform convention: UNKNOWN.** Nothing in the repo establishes whether the modelled platform
requires every starting slot filled. What is certain is the scoring consequence — an unfilled K
slot costs ~130 realized points, so it is never rational whatever the platform allows.

### Phase 2 — the structural rule, pre-registered before measurement (commit `30a0683`)

Replacement level is *the best player at a position who will still be undrafted when the draft
ends* — the classic VBD definition, made literal against the live board:

```
demand[p]      = players at p a full draft of THIS league consumes, per team
remaining[p]   = max(0, teams * demand[p] - drafted[p])
replacement[p] = the remaining[p]-th best AVAILABLE player at p (0-indexed)
```

`demand[p]` is obtained by running **one mock draft of this league on the preseason consensus
board alone** (`teams × roster_size` picks, best-available by ECR with the endgame mandatory-slot
reservation) and counting each position. `Σ demand[p] = roster_size` by construction — the
structural anchor, and the reason **there is no free parameter to tune**. Flex resolves itself
(slots go to whoever the board says). It is format-adaptive from config: measured on
`legacy_2qb_dynasty` it returns QB 3.5/team against the 1-QB league's 1.7. It is leakage-safe —
`load_market_ranks` is already restricted to the drafted season's Jul/Aug snapshots (D54).

Tiers, and the decision rule, both committed before any 50-draft run:

| tier | definition |
|---|---|
| W0 | control — shipped N4, static replacement |
| W1 | the structural rule alone |
| W2 | W1 + endgame mandatory-slot reservation (legality as a hard constraint) |
| W3 | legality **alone**, on static replacement — isolates it from any depth change |
| W4 | reference — D66's uniform ×2.5, unchanged |

Ship the **lowest-numbered** tier clearing every gate.

### Phase 3 — results (2021–2025 × 10 slots = 50 drafts/tier, fair opponent)

| tier | starter | vs W0 | 95% CI | W/L | seasons worse | infeasible | cap breaches | mean K | mean TE |
|---|---|---|---|---|---|---|---|---|---|
| W0 control | 2029.2 | — | — | — | — | 0/50 | 34 | 2.74 | 2.06 |
| **W1** | **2061.3** | **+32.1** | **[+11.5, +52.7]** | 24/20 | **1** | **0/50** | **1** | 2.02 | 2.16 |
| W2 | 2061.3 | +32.1 | [+11.5, +52.7] | 24/20 | 1 | 0/50 | 1 | 2.02 | 2.16 |
| W3 | 2029.2 | +0.0 | — | 0/0 | 0 | 0/50 | 34 | 2.74 | 2.06 |
| W4 (D66 ×2.5) | 2055.9 | +26.7 | [+7.1, +46.3] | 34/16 | 1 | 0/50 | 0 | 1.00 | 3.90 |

**Two findings worth stating plainly.**

**W3 is byte-identical to W0.** The legality constraint never fires — the static defect already
overvalues kickers enough to fill every mandatory slot. So legality contributed **exactly 0.0**
points, and W2 is byte-identical to W1 for the same reason. Legality is insurance, not a gain, and
it is not what was measured here. Per the pre-registered rule (lowest-numbered clearing every
gate) and the standing Occam tie-break, **W1 ships and the legality constraint does not.** It
stays available in the harness.

**W1 beats the D66 reference it was measured against.** +32.1 vs +26.7, on a rule with no
parameter versus one selected off a sweep. W4 still wins more often (34/16 vs 24/20) and carries
zero cap breaches to W1's one — W1 wins bigger, less consistently.

Gates, all pre-registered: G1 zero-rate at a mandatory position **0** at every position; G2
infeasible rosters **0/50**; G3 seasons worse **1** (limit 1); G4 positional timing, largest shift
0.8 rounds (limit 2.0); G5 cap breaches **34 → 1**, decreased; G6 leave-one-season-out
**+25.4 / +45.5 / +22.9 / +35.7 / +31.1**, positive on all five.

**G7, out-of-format** — `legacy_2qb_dynasty`, different lineup, roster size 17, different consensus
board, rule unchanged: W1 **+75.5, 95% CI [+38.6, +112.3], W/L 36/14**, against W4's +65.6. The
mechanism transfers to a format it was never tuned on — which, for a rule with no parameter, is
what it should do.

### What shipped

`league/draft.py`'s value base now measures its surplus term against the draft-aware level.
`vorp` stays **static** and continues to drive the D55 opportunity-cost replay, the reported
candidate field, and the candidate-universe filter — that term prices near-term availability
against a season-level scale and was measured that way, so re-basing it would silently change a
second mechanism. Only the value base moved, which is exactly the tier that was measured.

Three implementations were promoted or unified rather than duplicated:
`league/replacement.py::market_draft_demand` and `::demand_boundary_replacement` are now
production, with `evaluation/replacement_diagnostics.py` delegating to them; and
`league/opportunity_cost.py::roster_aware_market_pick` is the single canonical endgame rule, used
by the fair benchmark opponent *and* by the demand model. If those two ever disagreed about how a
draft consumes positions, the shipped replacement level would be measured against a draft nobody
plays.

Cost: ~11ms per recommendation for the mock draft, so it is computed per call rather than cached —
a re-ingest can never serve a stale target.

### A real bug this change introduced, found by the existing suite

Making replacement depend on `available_player_ids` gave that argument a second meaning it does
not always carry. `POST /league/{id}/draft` accepts an arbitrary set, and **a shortlist means
"the players I am asking about", not "the only players left in the league"**. Read as a board, a
three-player shortlist says almost everyone is drafted, so every position's remaining demand is 0,
replacement collapses to the best player in the shortlist, and the whole shortlist prices at zero
surplus — the engine stops discriminating entirely. Two pre-existing tests caught it
(`test_over_cap_position_is_heavily_discounted`, `test_the_two_engines_actually_disagree_here`).

Two structural guards, neither a tuned threshold, both verified to leave tier W1 **byte-identical
on real 2021–2025 data**:

1. **Boundary not on the board** (`demand_boundary_replacement`) — if `remaining_demand` exceeds
   what is available at the position, the boundary player does not exist to be observed, so the
   position is omitted and the caller uses the static level. Clamping to the worst available
   instead would hand every other player there a large spurious surplus. Never fires in a real
   draft: 0/800 real pick-states, every position, every depth up to ×3.0.
2. **Pool is not a board** (`league/draft.py`) — a draft removes at most `teams × roster_size`
   players, so a pool implying more than that cannot be a draft in progress and the whole
   draft-aware path is skipped. At the benchmark's last pick exactly `teams × roster_size` are
   gone, so this never fires there either.

One test fixture also had to change rather than the assertion:
`test_the_two_engines_actually_disagree_here` curated `available` down to four players in a 2-team,
4-round league, which now correctly reads as "every QB and RB slot in the league is filled" and
zeroes both positions' surplus. Restoring the omitted depth players to `available` restores the
discrimination the test exists to document.

### What remains UNKNOWN

- **Whether W1's shape is right or merely better.** W4's crude ~+100-point skill-position bonus may
  still be capturing something real that a correctly-shaped target does not. W1 beat it on both the
  primary metric and out-of-format, but W4 won more individual drafts.
- **Consumption when Alpha deviates.** `demand[p]` is measured from a 10-consensus mock, so it is
  exogenous by construction; how well it describes a draft where one seat plays differently is not
  measured.
- **Whether K/DST replacement means anything at any depth** — D57 measured year-over-year K r=0.41,
  DST r=0.29.
- **Platform legality convention**, per Phase 1.
- **Sample size** — five seasons, 50 drafts per tier.
