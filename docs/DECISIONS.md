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
