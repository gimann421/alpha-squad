# W16 — Controlled beta readiness, and the 2026 holdout

**Status:**

- **Beta:** an EXPERIMENTAL prospective weekly board exists and is usable now (2026 week 5).
- **Holdout:** no new week is eligible. The holdout is unchanged at 4 weeks: INCONCLUSIVE —
  CONTINUE.

**W10 is not validated on 2026.** The beta lets the user try it beside current Alpha while the
evidence accumulates. Decision record: D124.

**Production-path changes: none.** No existing production file, endpoint, CLI command or model
changed. All new code is beta-only and additive: `src/alpha_squad/beta/` (a new package that
nothing imports and no API route or CLI command exposes), `scripts/beta/` and `tests/beta/`.
Nothing on the research or production path imports it (tested).

---

## 1. Product readiness findings (audit of the actual repository)

### What exists

| item | finding |
|---|---|
| live weekly endpoint | `GET /rankings/weekly` (`api/routers/rankings.py`). A direct read of `weekly_projection_snapshot` for `ml_catboost`, plus M9's evidence deltas |
| model it serves | production's weekly CatBoost (`train established`): 11 features, QB/RB/WR/TE, walk-forward by season. **This is "current Alpha", arm A of W10/W14** |
| web UI | `web/` (Vite/React) has a "Weekly" panel inside Rankings over that endpoint. It is local-only (`make serve` + `make serve-web`) and needs a fully built database |
| W10 | research code only (`scripts/research/w10_historical.py` → `w9.durable_table/durable_panel` → `arms.train_with_extra_features`). RB/WR/TE only. **Never served by any product surface** |

### What prevents use: the old defect is still present

**1. Not prospective.**

- `weekly_projection_snapshot` rows exist only for `player_week_features` rows.
- Those exist only for players with a `player_week_stats` row, i.e. after the game is played
  (`features/panel.py`; W3 §2.1 documented this).
- So before kickoff the endpoint has **zero rows** for the coming week. Afterwards it ranks only
  the players who played, a selection on the outcome.
- The features themselves are leakage-safe: every window excludes the current row. Only a row's
  *existence* depends on the game.

**2. Positions.**

- No K or DST weekly projection exists anywhere (D57's baselines are season-level).
- No FLEX view: the endpoint offers a position filter only.
- W10 has no QB model.

**3. Scoring.** Both models are trained on the **Full-PPR** target only.

- The W14/W15 "Half-PPR" robustness cells ranked by those same Full-PPR predictions and scored
  them against Half-PPR outcomes.
- No Half-PPR projection exists.

**4. Availability.** Not shown. The endpoint has no bye, started-game or injury handling, because
it only ever has played rows.

**5. Data.** This container started with **no data at all**: `data/` is gitignored and the prior
session's databases are gone. The holdout's canonical database (sha256 `fa8e32db…`) went with them
(§3, §4).

### Can W10 safely power an experimental beta? Yes, with one bounded adapter

**The missing piece is only the prediction frame.** W10's and production's training are both:

- walk-forward;
- trained on seasons [2015, S-1];
- fit once per season.

So a model fit for 2026 never sees a 2026 row. What is missing is a week-*w* feature row for
players who have not played week *w*.

**The fix is an adapter, not a model change.** Separate the two pieces:

- **A. Experimental eligibility adapter** (new, beta-only):
  - the universe comes from the weekly roster and the schedule;
  - feature rows come from production's own feature builders, run over games before the week.
- **B. Frozen W10 and production models**, unchanged. Both arms are fit by calling W10's
  `arms.train_with_extra_features`:
  - with no extra columns, which is production's model exactly (W7's fidelity property);
  - with W10's 7 durable features, which is arm B exactly.

---

## 2. Beta implementation

### Changed files (all new, beta-only, plus one `.gitignore` allow-list)

| file | why |
|---|---|
| `src/alpha_squad/beta/prospective.py` | Prospective feature rows. Loads stats strictly before week *w* into an in-memory DB, appends a NULL-stat placeholder row per eligible player and per scheduled team, and runs production's unmodified `build_player_week_features`, `build_team_week_features` and `attach_team_features_to_player_panel`. `equivalence_check` proves the rows equal production's stored rows on a completed week |
| `src/alpha_squad/beta/weekly_board.py` | Pure product rules: the eligible universe (roster × schedule; byes, statuses, identity, started games, injuries), the Half-PPR conversion, FLEX, ranking, and snapshot assembly with a content hash id |
| `scripts/beta/weekly_board.py` | The runner. Every DB is opened read-only, both arms are fit in memory through the frozen functions, three fidelity checks are recorded, and a snapshot JSON + CSV is written |
| `scripts/beta/render_board_html.py`, `scripts/beta/board_template.html` | A self-contained viewer of a snapshot. It **displays** precomputed board orders and never re-ranks |
| `tests/beta/test_weekly_board.py` (20), `test_prospective.py` (7), `test_isolation.py` (8 incl. 3 parametrized) | §4 |
| `.gitignore` | allow-lists `reports/beta/weekly_board_*.json` (saved snapshots only) |
| `reports/beta/weekly_board_2026_w05_3731658a315d.json` | the first saved board |

### Product rules

**Universe:**

- the nflverse weekly roster at the cutoff (latest week ≤ *w*), statuses ACT and INA, QB/RB/WR/TE/K;
- one DST per scheduled team;
- **no stats row is required.**

**Excluded and counted, never silently dropped:**

- bye teams, taken from the season schedule;
- reserve, practice-squad, cut, retired and exempt statuses;
- unresolved identities.

**Projections:**

- **Current Alpha:** production's model.
- **W10:** arm B for RB/WR/TE. QB falls back to current Alpha, labelled "W10 has no QB model".
- **K/DST:** D57's season baseline ÷ 17, identical under both selections and labelled. It is not a
  weekly model and has no matchup adjustment.
- **No ECR input.**

**Expected points vs availability:**

- The projection is expected points *if he plays*.
- Roster status (INA) and the week's injury-report designation are shown beside it, never
  multiplied in. "Hide Out / inactive" is a display filter.

**Started games:** flagged by kickoff ≤ cutoff, and kept on the board. Their projections use only
earlier weeks. A display filter hides them.

**FLEX:** RB/WR/TE pooled by projected points.

**Half-PPR:** `full_ppr − 0.5 × receptions_avg_last3`, labelled an approximation on every row and
in the metadata. It is **not** a validated Half-PPR model; see §5.

**Ordering:** points descending, ties broken by `player_id`. The ranks are fixed for the whole
board.

**Explanations:**

- The viewer shows the model's actual inputs for a player:
  - recent usage;
  - team environment;
  - W10's 2025 features.
- They are labelled "what the models were given, not how each model weighed them".
- No narrative labels ("breakout", "great matchup") and no per-player attribution. No valid
  per-prediction attribution method exists here.

**Snapshot metadata:**

- snapshot id (sha256 of the content);
- beta version;
- both models (spec, features, training seasons, status);
- scoring definitions;
- cutoff (= generation time);
- each data source with capture time and sha256;
- the roster week used;
- exclusions;
- the fidelity checks.

### The first board: 2026 week 5, cutoff 2026-10-11 12:01:29 UTC

The cutoff is Sunday 08:01 ET, before every Sunday and Monday game.

| | value |
|---|---|
| eligible | 540: QB 81, RB 114, WR 172, TE 113, K 30, DST 30 |
| ranked with no 2026 game before week 5 | **80**. The old live path could rank none of them |
| started at the cutoff | 33, Thursday's game |
| bye | CAR, KC |
| excluded by roster status | CUT 13, DEV 165, EXE 1, RES 96, RET 8 |
| unresolved identities | 0 |
| no projection | 5 kickers with no prior NFL season (listed in `unprojected`) |
| injury designations shown | 46 |
| stats used | weeks 1–4 only (row-level `week < 5`; Thursday's week-5 game is in the database and is excluded) |
| snapshot | `3731658a315d67686244c7d054465656002ff9c8116acc6b2378e24dbcc57074` |

**How different the two boards are** (Full PPR):

| view | top-10 overlap (W10 vs Alpha) | mean / max \|Δ points\| |
|---|---|---|
| WR | 7 of 10 | 0.48 / 2.23 |
| FLEX | 8 of 10 | 0.42 / 3.55 |
| RB | 9 of 10 | 0.37 / 3.55 |
| TE | 8 of 10 | 0.39 / 2.69 |
| QB | 10 of 10 | 0 (same model) |

**How to access it:**

- **Viewer:** the private published page, https://claude.ai/artifact/1n2jfHLJ29ikVQMJ9zfiYi
  - board selector: W10 / Current Alpha / Compare (side by side, with rank movement and Δ points);
  - Full / Half PPR;
  - All, QB, RB, WR, TE, FLEX, K, DST;
  - started and injury filters;
  - search;
  - per-player inputs;
  - "Copy view as CSV";
  - a metadata panel.
- **Files:** the snapshot JSON is committed. To regenerate the CSV and HTML, run
  `uv run python scripts/beta/render_board_html.py <snapshot.json> --out <file.html>`.
- **Next week's board:** §5.

---

## 3. Frozen validation update

### Is a new week eligible? No

The eligible-week list was frozen before any scoring. Only schedule columns of a fresh nflverse
schedule snapshot were read (captured 2026-10-11 11:49 UTC, sha256 `5f1484b2…`).

| week | games | last kickoff (ET) | status at 2026-10-11 07:49 ET |
|---:|---:|---|---|
| 1–4 | 16 each | ≤ 2026-10-05 20:15 | already evaluated (W14, W15) |
| 5 | 15 | **2026-10-12 20:15** (Monday) | **not eligible.** Sunday and Monday games unplayed; fails §4 conditions 2–4 |
| 6–17 | — | — | not played |

**No holdout run was made, and none was permitted.**

- `reports/weekly/w14_results.json` and `w15_results.json` are byte-unchanged (pinned by test).
- The verdict stands: **INCONCLUSIVE — CONTINUE, 4 eligible weeks of the 8 needed**.

### Can the beta alter the frozen validation? No: four separate guarantees, all tested

1. **No import path.** No file in `scripts/research/` or `src/alpha_squad/` (outside `beta/`)
   imports the beta (`test_no_research_or_production_module_imports_the_beta`).
2. **W10's code is untouched.** Every file on W14 gate G2's W10 path is identical to `5de17c1`
   (`test_w10_frozen_code_path_unchanged_since_w10_commit`, using G2's own list).
3. **The frozen artifacts are untouched.** w10, w14 and w15 results are pinned by sha256.
4. **Read-only runner.** It opens every database read-only and fits nothing of its own: every fit
   is a `train_with_extra_features` call with `[]` or W10's frozen 7 features (AST-checked). Beta
   snapshots go to `reports/beta/` and are never holdout inputs. Only the W14 runner on a §3
   isolated ingest produces holdout observations.

**The beta runs exactly the code and specifications the holdout evaluates, on this session's
data.** On the completed week 4, inside the beta run (see the next subsection for the limit: the
rebuilt history reproduces production exactly, but not W10's committed fits):

| check | result |
|---|---|
| prospective features vs production's stored features | **3,938 / 3,938** cells exact (358 players). Also 15,092 / 15,092 on 2025 weeks 1, 2, 10, 17 |
| beta current-Alpha predictions vs production's stored `ml_catboost` predictions | **358 / 358** exact, max diff 0.0 |
| beta W10 predictions vs W10's frozen arm-B training line, with W10's own `op.build_panel` | **324 / 324** exact, max diff 0.0. The same 324 week-4 player-weeks W15's G6 counted |
| training frames vs base database (production's loader) | identical, QB/RB/WR/TE |
| determinism | regenerating with the same cutoff is **byte-identical** |

### The canonical database is gone (affects the next look, not this one)

- W14 §3 and gates G3, G4 and G12 reference `data/alpha_squad.duckdb` with sha256 `fa8e32db…`.
  That file no longer exists in any reachable environment.
- This session rebuilt it from sources:
  - `sources ingest`, `identity build`, `features build` and `train established`, 2015–2025;
  - sha256 `8b6cca85…`.
- A DuckDB file's bytes are not reproducible, so **G4's hash check cannot pass as written at the
  next look.** The substantive question is whether the rebuild is *equivalent*.

**Measured:** W10's committed runner (`w10_historical.py`, 2021–2025) was re-run on the rebuilt
database and compared with the committed `reports/weekly/w10_results.json`. **It is NOT
byte-identical.**

| | committed (canonical DB) | rebuilt DB |
|---|---:|---:|
| W10 verdict, Full and Half PPR | SUCCESS (WR c@10, WR c@5) | SUCCESS (WR c@10, WR c@5), no breach |
| WR capture@10, B − A | +0.0223 | **+0.0291** |
| WR capture@5, B − A | +0.0275 | +0.0302 |
| RB capture@10, B − A | +0.0004 | −0.0024 |
| arm A (current Alpha) and ECR cells | — | **identical in every week** |
| W10-family arms (B, null, three ablations) | — | differ in essentially every week, 2021–2025 |
| snapshot provenance (injuries, depth, ep sha256s) | — | identical |

**What this establishes:**

- **The rebuild reproduces production exactly** (arm A), including the training-frame order that
  A2 showed moves CatBoost fits.
- **It does not reproduce W10's fitted arms.** Something only the W10 arms read differs between the
  canonical and rebuilt histories. The candidates are the durable table's prior-season inputs or
  the W10 panel's key set. Most likely it is an upstream nflverse revision of 2015–2025 stats
  columns that production's 11 features do not use the same way.
- **It cannot be root-caused here.** The canonical database no longer exists to diff against.
- **W10's historical conclusion is unchanged in direction and verdict;** its size moves within its
  own CI.

**Consequences:**

1. **For the beta.** The beta's W10 board is W10's exact code and specification, trained on this
   rebuilt history: 324/324 matches W10's own training line on the *same* database. It is **not
   shown to be bit-identical to the W10 model fitted inside W15's environment.** That is
   acceptable for an experimental board. It is recorded here and in D124; the week-5 snapshot's
   metadata predates this finding and does not carry the caveat.
2. **For the holdout.** The next look cannot pass G12 (W5–W13 byte-identical) or G4 (canonical
   hash) on this base as written. Before any week-5+ data is ingested, it needs one of:
   - **(a)** recover the canonical database. No copy is known to exist.
   - **(b)** a dated pre-data amendment A6. It would:
     - adopt a rebuilt base;
     - replace G12's byte-identity with an explained-difference check like A4's, which requires a
       root cause of the W10-arm difference, named before any new 2026 result;
     - **re-score weeks 1–4 on the new base** and report them beside looks 1–2.

     No rule, metric, model, feature or eligibility change.
   - **(c)** a written decision that the holdout's W10 arm is "W10's specification refit on the
     current upstream history". This is defensible, since a real 2026 deployment would refit
     anyway, but it is a protocol change and must be pre-registered.

   **This is a decision for the user. It does not block the beta.** This session writes no
   amendment, because no look is due and the choice is not technical.

---

## 4. Tests

| requirement | test(s) |
|---|---|
| **A. Frozen validation integrity** | |
| W10 implementation unchanged | `test_w10_frozen_code_path_unchanged_since_w10_commit` |
| frozen artifacts unchanged | `test_frozen_validation_artifacts_unchanged` (w10, w14, w15) |
| beta cannot alter validation | `test_no_research_or_production_module_imports_the_beta`, `test_beta_runner_opens_databases_read_only`, `test_beta_runner_fits_through_frozen_functions_only` |
| row-order restore deterministic | runtime: A2's `loader_matches_canonical` all True on the beta DB; `training_frame_identical_to_base` in the snapshot |
| later outcomes cannot move earlier predictions | `test_week_and_later_outcomes_cannot_move_prospective_rows` (same week-3 rows before and after weeks 3–5 exist) |
| **B. Prospective board integrity** | |
| players without same-week stats appear | `test_player_without_any_stats_is_eligible`, `test_player_who_never_played_gets_a_row_not_dropped`, `test_prospective_week_needs_no_stats_row_for_that_week` |
| no post-cutoff information | stats filtered by week (`_history`); roster and injury snapshots captured after the cutoff are refused (`_snapshot_meta`); later-week invariance test above |
| bye weeks | `test_bye_week_players_are_excluded_and_counted`, `test_bye_teams_come_from_the_schedule_when_the_roster_omits_them` (regression for the real week-5 bug below) |
| started games | `test_started_games_are_flagged_by_kickoff_vs_cutoff`, `test_kickoff_is_eastern_time_and_requires_a_time` |
| missing features do not drop players | `test_missed_game_player_keeps_history_and_stays_eligible`; the runner raises if any eligible player lacks a row or a prediction; `test_missing_prior_season_uses_w10s_own_no_prior_values` |
| identity | `test_identity_keys_are_canonical_ids_and_dst_from_team_code`, `test_unresolved_identity_is_reported_not_dropped_silently`, `test_duplicate_player_on_roster_raises` |
| FLEX is RB/WR/TE | `test_flex_contains_only_rb_wr_te` |
| Full / Half PPR | `test_half_ppr_is_full_minus_half_recent_receptions`, `test_board_sorted_by_selected_model_and_scoring_with_id_tiebreak` |
| **C. Product integrity** | |
| model selector | `test_snapshot_boards_match_the_selected_models_projections`, plus the runtime fidelity checks (358/358, 324/324) |
| position filters, sorting | `test_position_filters_and_overall`, `test_board_sorted_by_selected_model_and_scoring_with_id_tiebreak`, `test_unknown_board_rejected` |
| metadata | `test_snapshot_metadata_identifies_models_scoring_cutoff_and_is_experimental` |
| errors surfaced | missing kickoff time, duplicate games and duplicate roster entries raise; post-cutoff snapshots refused |
| **D. Reproducibility** | `test_snapshot_is_deterministic_and_identified`; real board regenerated byte-identical |

**Gates:**

- `make test`: **1,942 passed**, 0 failed (W15: 1,907; +35 beta tests).
- `make lint`: clean. `ruff check scripts/beta`: clean.

**Bugs found and fixed during W16, each with a regression test:**

1. **Bye teams were invisible.** nflverse's weekly roster omits teams on bye entirely (2026
   week 5: 30 of 32 teams), so a bye list built from roster teams was empty while CAR and KC were
   on bye. They now come from the season schedule.
2. **Prospective "no prior season" encoding.** W9's durable table has no (player, 2026) row for a
   player with no 2025 games who has not yet played in 2026, so W10's 7 inputs would have been
   all-NaN. In the holdout every such player has played, so he gets W10's own `has_prior = 0`
   values. The beta now assigns exactly those, from W10's `durable_features([], None)`.
3. A test that pinned the number of fit call sites was replaced by a stricter AST check of what
   each call fits.

---

## 5. Remaining blockers and limitations

**Before calling anything production:**

1. **The holdout's base database is lost (§3).** The rebuild reproduces production exactly but
   not W10's committed fits (WR capture@10 +0.029 vs +0.022, same verdict). The next look needs a
   pre-data decision from the user.
2. **W10 is unproven on 2026.** It has 4 of the 8 weeks needed for any directional reading, and the
   final rule applies after week 17. Nothing in this beta changes that.
3. **Half-PPR is an approximation.**
   - A real Half-PPR board needs either a Half-PPR-target model or a validated receptions
     estimate. That is a new modelling question and would need its own pre-registration.
   - The W10 FLEX top 10 differs between Full PPR and the approximation in 3 of 10 places this
     week.
4. **K/DST are season baselines ÷ 17.** They have no matchup or in-season information, and every
   week's K/DST order is nearly static.
5. **Weekly refresh is one command (D125):**
   `uv run python scripts/beta/refresh.py --season 2026 --week <N> [--html]`. It verifies the
   base hash `fa8e32db…`, works on a fresh hash-checked copy under `data/beta/`, runs A2 between
   `features build` and `train`, refuses holdout paths, and re-checks the base hash at the end
   (`tests/beta/test_refresh.py`). It wraps the manual steps it replaced:
   - a §3-style ingest into `data/beta/`;
   - A2's restore;
   - `train established`;
   - `scripts/beta/weekly_board.py`;
   - render and publish.

   A week-6 board should be generated **after** Monday's week-5 game and before Thursday 10-15's
   kickoff.
6. **Rebuilding the base costs one full ingest** (~10 minutes) in a fresh container, because no
   database persists between sessions.
7. **The local web app does not show the beta.** Adding a beta route and view would be a
   production-path change, deliberately left out of this scope.
8. **Roster timing.** The board uses the latest published weekly roster. Early in a week that is
   the previous week's, and the snapshot records which. Trades after it are missed.

---

## 6. Next decision

- **For the user:** use the week-5 board now (Sunday and Monday games), labelled experimental.
  Decide whether to ask for a week-6 board after Monday night.
- **For the holdout:** at the next look (week 5 eligible after Monday's game plus the nflverse
  publication lag):
  1. the user chooses (a), (b) or (c) from §3, because the canonical database is lost and the
     rebuild does not reproduce W10's committed fits;
  2. the chosen amendment is committed before any week-5+ ingest;
  3. then the unchanged W14 runner and gates run on a fresh isolated ingest.

  The first look able to read a direction has ≥ 8 weeks. The final look comes after week 17.

---

## LAYMAN'S TERMS

**What Claude did:**

- Checked the real app and found its weekly rankings only list players *after* their games are
  played, so it could never give you a board before kickoff.
- Built a separate, clearly labelled experimental board for this week that ranks every rostered
  player before games start. It lets you flip between the new W10 model and today's model, Full or
  Half PPR, any position or FLEX. It checked that both models run exactly the code being tested.
- Confirmed no new week has finished yet (week 5 ends Monday night), so the official 2026 test was
  left untouched.

**What it means:**

- You can use Alpha's week 5 rankings today, as an experiment. W10 still isn't proven, and the
  official test keeps running separately, unaffected.
- The old test database was lost with the previous session. A rebuild matches today's model
  exactly but nudges W10's historical numbers (same conclusion), so you'll need to pick how the
  official test continues before its next check.

**Next step:**

- Try the board for this week's lineups, and after Monday night ask for a week 6 board; the
  official test resumes once week 5's data is complete.
