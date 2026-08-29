# Alpha Squad — Implementation Gap Analysis

Companion to `docs/CURRENT_STATE_AUDIT.md`. Originally written 2026-08-24 (commit `e0ca6c3`);
refreshed 2026-08-25 after a P0-P8 hardening pass (`docs/DECISIONS.md` D41-D52) closed every item
except P2-3, which needs a user decision. Each item still reflects what is **actually missing today** — not a
re-statement of the original spec. Closed items are kept (marked `CLOSED`, struck through) rather
than deleted, so this file stays an accurate record of what was found and what changed, not just a
snapshot of what's currently outstanding. Items are ordered P0 (do first / highest risk) → P3
(nice-to-have / low risk). "Dependencies" lists other items in this file that should land first;
items with no listed dependency can start immediately.

---

## P0 — Do first

### ~~P0-1: Resolve the leaked-credential Git-history exposure~~ — CLOSED (D42), decision confirmed already made in D35

- **What was found:** Real API key values from the D35 incident remain permanently retrievable via
  `git log --all -p -- .env.example`. Originally flagged as needing a decision with the user's
  explicit sign-off on whether to rewrite Git history.
- **What actually happened:** Re-reading D35 itself (not reopening it) found the decision was
  already made at the time of the original leak — the user was offered a full `git filter-repo` +
  force-push history purge and **explicitly declined it**, reasoning it is strictly more invasive
  than the file fix and still wouldn't undo the actual exposure (only provider-side key rotation
  does that). D42 confirmed this and added a durable, non-destructive guardrail instead:
  `scripts/check_no_secrets.py`, wired into `make lint`/CI, fails the build if a tracked
  `*.env.example` file ever gets a real secret-shaped value again — verified against a synthetic
  fixture reproducing D35's exact pattern.
- **What remains, if anything:** This repo cannot verify whether the user has actually rotated the
  two leaked keys at their respective providers — that was, is, and remains outside what static
  analysis of this repo can check. If a future session or the user wants to reopen the
  history-rewrite question, that requires a fresh, explicit request — it is not something an
  autonomous session should revisit on its own read of "more time has passed."

---

## P1 — High value, ready to build

### P1-0: Fix `recommend_draft_pick`'s roster-balance failure — **REOPENED (D61)**

> **REOPENED.** This item was closed at D60 on a benchmark whose `market_consensus` opponent
> drafts 0.00 kickers and 0.30 defenses per draft, leaving two of its ten starting slots empty
> — an artifact worth **+245.3 starter points**, more than the entire +165.7 margin the closure
> relied on. Against an opponent that merely fills those slots, Alpha scores **−48.3 with a
> 25/50 (50%) win rate**, 95% CI [−122.2, +25.6]. On the eight skill slots Alpha is **79.6
> points behind**. The acceptance criterion below ("beats market consensus") is therefore
> **not met**. Full evidence: `docs/DRAFT_STRATEGY_FORENSIC_ANALYSIS.md`; decision: D61; the
> path forward: `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`.
>
> The D54 and D55 mechanism fixes remain real. What is retracted is the *claim of
> outperformance*, not the underlying engineering.
>
> **Update (D62):** the D61 estimate above was a targeted re-simulation; Stage 1 of
> `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md` has now shipped the fix into the real benchmark
> code (`market_consensus_roster_aware`) and re-run it against real 2021–2025 data. Measured
> directly: **Alpha −45.4 mean starter points vs. the fair opponent, 25/50 win rate, 95% CI
> [−117.1, +25.6]** — confirming D61's estimate to within 3 points. **Still not met.** Stage 1
> is measurement-only by design (see D62); no engine change has been attempted yet.
>
> **Update (D63):** Stages 2 and 3 have now run, and the engine change shipped. The value base
> became `marginal_starter_value + VORP`, chosen by a 500-draft ablation under a rule
> pre-registered in git before any run. Against the fair opponent Alpha improves from **-45.4
> to -5.6** mean starter points (95% CI [-68.4, +57.2], win rate 25/50) — **88% of the gap
> closed, and the floor rose from 1570.3 to 1765.3 with stdev falling 160.8 to 131.7.**
> **Still not met:** the margin is negative, the win rate is 25/50, and the interval contains
> zero. P1-0 stays OPEN. The leading remaining defect is that the new blend over-drafts kickers
> (the K cap is breached in 32 of 50 drafts) — see D63.
>
> **Update (D64):** that kicker regression was investigated and **no change shipped**. Tracing a
> real hoarding draft showed the cause is a *stale replacement level*, not flex-eligibility:
> late in a draft MSV is 0 for everyone, so the base collapses to VORP, and VORP's static
> preseason replacement level makes the stripped skill pools look below-replacement while the
> untouched kicker pool stays above it. Tightening the over-cap multiplier is provably inert
> (margin exactly +0.0, 0/0 W/L — the second kicker is taken while *under* the cap). Saturating
> the VORP surplus fixed roster shape dramatically (cap breaches 34 → 4) but scored only +1.3
> (CI [−32.0, +34.6]) while losing 27 of 50 drafts, failing two robustness gates. Alpha remains
> **−5.6** vs fair consensus, 25/50. **P1-0 stays OPEN.** Highest-value next step: draft-aware
> replacement levels (recompute replacement against the *currently available* pool).

> **The benchmark below is invalid for the current target format and is preserved as-is,
> labelled, not restated.** Everything through "Acceptance criteria — STILL UNMET" was
> measured against `ecr_type='rsf'` — FantasyPros' *superflex* board — because the target
> league was then 2QB (D7/D21). The product's target format is now a 10-team 1-QB redraft
> league (`docs/TARGET_FORMAT_1QB.md`); its matching board is `ro` (D56). Re-baselined on the
> correct board, `alpha_league_aware` beats `market_consensus` outright — see the update at
> the end of this item and `docs/FORMAT_MIGRATION_DIAGNOSTIC.md` for the full account. Both
> mechanisms below (D54/D55) remain real fixes for the pathologies they addressed; they are
> not undone, only re-measured against the right opponent.

- **What was found:** A real historical draft simulation (`src/alpha_squad/evaluation/
  draft_simulation.py`, `docs/DECISIONS.md` D54) showed the actual production draft
  recommender (`alpha_league_aware`) losing to plain market consensus on mean starter points
  in **every one of the 5 real seasons tested** (2021-2025, pooled 1644.5 vs. 2020.7),
  never winning a single season outright, and scoring below `alpha_bpa` (identical player
  values, no league context) on pooled *total* roster points (2680.0 vs. 2756.1) — though it
  *beats* `alpha_bpa` on pooled *starter* points (1644.5 vs. 1429.1), so league-aware context
  is not making every decision worse, just net worse overall. Root-caused by inspecting real
  drafted rosters: the recommender drafted 7 QBs and zero RBs into a league starting 2 of each
  in one real 2021 trial, and 12 WRs against only 3 QBs in a real 2025 trial. These specific
  numbers were re-verified after fixing two real bugs found via a follow-up leakage/
  reproducibility audit of the draft-simulation path itself (a missing season filter in
  `next_pick_survival_probability`, and non-deterministic tie-breaking over Python `set`s) —
  the numbers above are the corrected, reproducibility-confirmed (byte-identical across two
  separate process runs) result, not the original ones. The specific "7 QB / 0 RB" and
  "12 WR / 3 QB" rosters were then further verified by directly replaying the real
  `recommend_draft_pick` function pick-by-pick against real 2021/2025 data (prompted by a
  direct question of whether such a roster is even plausible for a real fantasy draft — it
  is, and the replay pins down exactly why).
- **Why it happens — two compounding mechanisms, both confirmed by the replay, not inferred
  from the final roster alone:**
  1. `roster_fit_multiplier` in `league/roster.py` is bounded to [0.7, 1.3] by design, but its
     real per-pick penalty growth is far gentler than that bound implies: even after already
     drafting 6 QBs, a 7th costs only a **6% discount** (`fit_mult=0.94`, verified by direct
     computation of the formula), nowhere near the 0.7 floor and nowhere near enough to
     overcome a real VORP edge (round 1 of the replayed 2021 draft: an available TE at 127.5
     VORP and QB at 131.2 VORP both beat the best available RB at 103.1, before any
     roster-need adjustment at all).
  2. The other 9 draft slots (real market-consensus opponents) drain the underdrafted
     position at a normal, balanced rate throughout the draft. Because this team's early picks
     drifted toward QB/WR/TE, by round 16 of the replayed 2021 draft the best *available* RB
     had VORP **-135.4** — worse than replacement level. By the time roster-need pressure
     would organically demand an RB, none were left to correct with. `roster_fit_multiplier`
     only reacts to current roster composition; it has no way to anticipate a run depleting a
     position it hasn't drafted yet.
  Bench players who never start still count toward `total_roster_points`, which is why the
  total-points shortfall (255.1 pts pooled) is smaller than the starter-points shortfall
  (376.2 pts pooled) — the value is there, just stranded on the bench.
- **Mechanism 1 — FIXED and re-verified against a full re-run of `alpha-squad evaluate
  draft-simulation`, not just unit tests.** `roster_need`'s oversaturation coefficient was
  steepened (-0.2 -> -3.0 per player beyond starters + a healthy 2-deep bench) so
  `roster_fit_multiplier` hits its 0.7 floor immediately at one player past a full bench,
  instead of requiring ~15 extra players. Regression test added and confirmed to fail against
  the old coefficient. Real, measured effect of the fix (before -> after, pooled): mean
  starter points 1644.5 -> 1688.2 (+2.7%, a real gain in the metric that actually determines
  fantasy outcomes); mean total roster points 2680.0 -> 2606.6 (-2.7%, a real tradeoff — less
  value stranded on an over-drafted position's bench, but the roster leans on lower-value
  players at other positions to get there); the replayed 2021 slot-1 roster's QB count dropped
  7 -> 6. **This does not close the gap to `market_consensus`**: `alpha_league_aware` still
  loses every one of the 5 seasons on starter points (0/5 wins, unchanged) and still trails by
  332.5 pts pooled (down from 376.2 — roughly 12% of the original gap closed). The 2021 slot-1
  roster still drafted **zero RBs** even after the fix — direct, concrete confirmation that
  mechanism 2 is untouched, since a same-position saturation penalty cannot help a position
  the engine never drafted at all. The 2025 slot-1 roster did rebalance meaningfully (RB count
  1->2, WR count 12->9), so the fix is a real, partial improvement, not a no-op.
- **Mechanism 2 — still open, now diagnosed in depth by a dedicated forensic phase (M17)
  before any further fix, rather than guessed at.** Full account: `docs/DRAFT_ENGINE_FORENSIC_AUDIT.md`,
  `docs/DRAFT_CONTROLLED_EXPERIMENTS.md`, `docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md`. Key
  findings that sharpen the diagnosis above: (a) replaying the real `recommend_draft_pick`
  pick-by-pick shows both traced pathological drafts are effectively decided by the team's
  *first 1-2 picks* — a real, viable RB is a live top-5 candidate at pick #1 and falls out of
  consideration entirely by the team's second turn, not a slow multi-round feedback loop; (b)
  `positional_scarcity()`, a real production function `PRODUCT_SPEC.md` requires and the waiver
  engine already consults, is never imported by the draft engine at all — a genuine, previously
  undocumented gap; (c) 90 real homogeneous-league drafts under 3 independent non-Alpha
  strategies never produced a zero-RB roster, validating the simulator and ruling out both it
  and the player-projection model as causes; (d) a full-scale controlled ablation (400 real
  drafts: 5 seasons × 10 slots × 8 tiers) confirmed the failure generalizes but is
  season-concentrated — the current production engine zeros RB in 10/50 trials, all of them the
  real 2021 season (10/10 slots that year, 0/10 every other season) — and found that adding
  positional scarcity or analytical future scarcity made the RB=0 rate *worse* (32% vs. 20% with
  neither), because `positional_scarcity()` rates QB, not RB, as the scarce position in this
  league's real data, reinforcing the QB-stacking side of the same pathology. Only an explicit,
  continuously-priced opportunity-cost term reduced the RB=0 rate to 4% and beat the current
  production engine on mean starter points (1789.1 vs. 1688.2 pooled, winning 4 of 5 real
  seasons). The recommended next step (not implemented, per the diagnostic phase's own scope) is
  an explicit per-position opportunity-cost term, continuously priced, using an opponent-behavior
  replay as its input, applied directly to the existing production formula — deliberately without
  adding `positional_scarcity`, now shown to backfire — see the redesign recommendation doc for
  the full reasoning.
- **Dependencies:** None — the evaluation harness to verify a fix already exists, mechanism 1's
  fix demonstrates the verify-with-a-real-rerun workflow to follow for mechanism 2, and M17's
  diagnostic harness (`src/alpha_squad/evaluation/draft_forensics.py`) already has the
  opportunity-cost mechanism implemented and unit-tested in isolation — it has not been ported
  into production `league/draft.py`, which is the actual remaining work.
- **Mechanism 2 — FIXED (M18 / D55) and measured on the official benchmark.** A continuous,
  points-denominated positional opportunity-cost term fed by a literal opponent replay
  (`league/opportunity_cost.py`), integrated as `(VORP + opp_cost) × fit × risk × survival`,
  plus a league-derived positional feasibility cap. Chosen by a pre-registered P-tier ablation
  (300 real drafts) rather than by implementing the redesign recommendation as written — that
  document's proposed formula turned out never to have been measured. Full 2021-2025 benchmark:
  mean starter points **1688.2 → 1801.1 (+112.9)**, RB=0 rosters 10/50 → 2/50, 7-and-8-QB
  rosters eliminated, all 10 draft slots improved, determinism verified byte-identical across
  processes, runtime +3.4%.
- **Acceptance criteria — STILL UNMET, and this item stays open.** The bar was:
  `alpha_league_aware` beats or matches `market_consensus` on mean starter points across the
  same 5 real seasons, without re-tuning the evaluation to produce that result. After both
  fixes Alpha reaches 1801.1 against market consensus's 2020.7 — a 219.6-point shortfall, and
  it has still never won a single season outright. The two identified mechanisms are now
  genuinely fixed (worth +156.6 combined), so the remaining gap is **not** attributable to
  either of them, and no further draft-scoring mechanism is currently evidence-backed as the
  next step.
- **Recommended next action (changed):** stop adding scoring mechanisms on intuition. The two
  wins so far both came from diagnosing first and measuring against a pre-registered rule. The
  defensible next step is another targeted diagnostic — establish where the residual 219.6
  points actually come from (D55 notes 2023 regressed while four seasons improved, which is
  itself an unexplained signal) — rather than a third mechanism chosen by plausibility.
- **UPDATE (D56–D60) — the diagnostic above was answered, and it closed this item.** Auditing
  whether the benchmark itself was appropriate for the incoming 1-QB target format (per an
  explicit directive not to assume it was) found the answer to the "residual 219.6 points"
  question directly: **the entire benchmark above was invalid.** `ecr_type='rsf'` is
  FantasyPros' *superflex* board (verified: 9 of the real preseason-2024 overall top 15 are
  QBs), which was the correct board while the target league was 2QB (D21) and the wrong one
  now that the target format is a 1-QB redraft league (`docs/TARGET_FORMAT_1QB.md`, D58). A
  second, independent bug compounded it: `ecr_type` alone is not a rank space — DynastyProcess
  labels an IDP board with the same `ecr_type` as the real PPR board, and the pre-D56 primary
  key silently dropped one of the two whenever they collided (D56).
  Re-baselined on the corrected `ro` board, under the corrected 1-QB league config, with
  **no change to the scoring formula**: `alpha_league_aware` **already beat** market
  consensus — 1927.8 vs 1825.2 mean starter points (+102.6, +5.6%), 34/50 (68%) win rate at
  the (season, slot) level, winning 4 of 5 seasons (D59). The M-tier ablation then asked
  whether the diagnosed gap in *this* item — the engine's score having no representation of
  the team's own starting lineup — still applied under the new format, rather than assuming
  it did: it did, and fixing it (marginal starter value replacing VORP as the score's value
  base, D60) pushed the margin further. **Full official benchmark, both seasons and the
  determinism requirement, verified:**

  | Strategy | Mean starter pts | vs. consensus |
  |---|---|---|
  | `alpha_league_aware` (D60, shipped) | **1990.9** | **+165.7 (+9.1%)** |
  | `market_consensus` | 1825.2 | — |

  Win rate at the (season, slot) level: **37/50 (74%)**. Per-season: wins 4 of 5
  (2021/2022/2023/2025); 2024 is a near-miss (1867.8 vs 1877.9, −10.1 — down from D55's
  −80.1 under the same board). Determinism: two separate-process runs of the official
  benchmark are byte-identical (`md5 5e0ec53e...`, matching across both files). The M-tier
  ablation additionally surfaced and fixed a real defect neither D54 nor D55 touched: the
  VORP-based formula drafted a mean 3.78 kickers and 2.26 defenses per 16-round draft, because
  VORP prices a bench K/DST against league-wide replacement level with no knowledge that
  neither position has flex eligibility — a "good" bench kicker scored positive VORP despite
  zero chance of ever starting. Marginal starter value has no such blind spot by construction.
  **Acceptance criterion met**, on the format the product now targets: `alpha_league_aware`
  beats `market_consensus` on mean starter points, without re-tuning the evaluation to produce
  that result — the fix that closed it (D60) was selected by a pre-registered decision rule
  measured against the corrected benchmark, not chosen to hit this target. Full account,
  including the pick-level attribution of what's still driving the residual per-pick variance
  and the 2024 near-miss: `docs/FORMAT_MIGRATION_DIAGNOSTIC.md`.

### ~~P1-1: Wire waiver, trade, and roster-need recommendations into the web UI~~ — CLOSED (D44)

- Waiver, trade, and roster-need are all wired into the SPA (`WaiverView.tsx`, `TradeView.tsx`, a
  roster-need section in `LeagueView.tsx`) and live-verified against a real Sleeper league
  (`dilworth`, season 2025) with real recommendations, real reasons, and real decisions recorded.
  D48 additionally replaced those views' raw opaque-player-id text entry with a real name-search
  picker (`PlayerPicker.tsx`, against the previously-dead `GET /players` endpoint), and fixed a
  real bug found doing it (an HTML `<label>`-click-forwarding issue that silently reset the
  picker's selection).

### ~~P1-2: Commit an EDGE historical-backtest report artifact~~ — CLOSED (D41)

- `alpha-squad edge backtest` + `market/edge.py::write_edge_backtest_report` produce
  `reports/edge_backtest.md`: real per-position, per-season, and edge-magnitude-bucket numbers
  (not aggregate-only), reusing the existing walk-forward methodology rather than a new one. Real
  result: BUY beat market-implied points in all 4 scored seasons 2022-2025; SELL was genuinely
  mixed. `docs/TRACEABILITY.md` updated to cite it. (Reports remain gitignored per CLAUDE.md's own
  policy — "commit the artifact" in practice meant "make the report-generating code real and
  reproducible," which it now is; nothing under `reports/` was ever meant to be committed.)

### ~~P1-3: Add model-artifact persistence for production model versions~~ — CLOSED (D43)

- `models/persistence.py` (generic CatBoost save/load + a `model_registry` upsert carrying
  `artifact_path`/`calibration_residuals_json`) closes this for the two paths that actually serve
  live predictions: uncertainty (`run_uncertainty(persist=True)` + `score_with_persisted_model`,
  backing `/rankings`) and the forward rookie projection (`project_rookie_class(persist=True)` +
  `score_rookie_projection_with_persisted_model`, backing `/rookies`). Verified against the real
  database: trained and persisted real models, then re-scored real players from the saved
  artifacts alone (no `.fit()` call) and reproduced the exact training-time output. New CLI:
  `alpha-squad models rescore-uncertainty` / `rescore-rookie-projection`.
- **Scope decision, not a gap:** established-player season-level/weekly models were deliberately
  left unpersisted — nothing in the API serves their output live today (it feeds
  `evaluation_results` for reporting/comparison only), so persisting them would add a servable
  artifact nothing reads. Revisit if `/rankings` is ever extended to read established-model output
  directly.

### ~~P1-4: Wire the Monte Carlo simulation engine into the API/UI~~ — CLOSED (D49)

- `POST /simulate/team-season` wraps the exact `simulate_team_season` the CLI calls (no parallel
  logic), plus a new `SimulationView.tsx` tab. Verifying it live surfaced a real, separate gap:
  `team_week_points` (the real-final-score table the simulation's covariance draw depends on) was
  completely empty in this deployment — `build_team_week_points` existed and was tested but had
  never been wired to a CLI command, so it never survived a database rebuild. Fixed the root
  cause: added `alpha-squad features build-team-scores` + a `make team-scores` runbook step, then
  ran it for real (7,326 rows, matching `team_week_stats`). Verified end-to-end via both the CLI
  and the running app (Playwright): a real KC/2025 simulation returns real named players (Patrick
  Mahomes, Travis Kelce, ...), real uncertainty bands, and a real QB/WR1 stack correlation
  (0.335), with a real persisted `team_simulation_runs` row.

---

## P2 — Real gaps, lower urgency

### ~~P2-1: Feed evidence-adjusted projections into what's actually served~~ — CLOSED (D46)

- Re-checked the architectural intent before resolving this (rather than assuming either branch):
  PRODUCT_SPEC.md's Evidence section says "current information updates the prior; it does not
  automatically override it," and ARCHITECTURE.md's pipeline places Evidence upstream of "Universal
  Player Intelligence" — evidence is supposed to reach served output. The real blocker wasn't
  missing logic: `weekly_projection_snapshot` (the table the real evidence-adjustment pipeline
  depends on) had never been populated in this deployment. Fixed by running the real weekly
  pipeline + evidence adjustment against 2025 data (6,037 predictions, 291 real deltas, 95
  materially adjusted) and adding `GET /rankings/weekly` (ordered by the evidence-adjusted value,
  with real reasons) + a "Weekly" mode in `RankingsView.tsx`. This closed the audit's separately-
  tracked "in-season/ROS" gap (P3-3 below) at the same time, since it was the same root cause.

### ~~P2-2: Implement future-draft-pick valuation in the trade engine~~ — CLOSED (D45)

- `LeagueContext.future_picks` turned out to be **always empty** in this deployment (no
  traded-picks data source is wired for Sleeper or the static YAML leagues) — wiring logic to read
  an always-empty field would have been dead code. Instead: `pick_value(round, teams,
  pick_in_round, years_out)` (a documented heuristic, same treatment as the pre-existing age
  curve, anchored to real `dynasty_values.value_2qb` data) + `evaluate_trade_package` (sums real
  player + pick value on each side of a trade) + `POST /league/{id}/trade-package` +
  `alpha-squad league trade-package`. Pick assets are explicit caller input, the same pattern
  `draft.py`'s `available_player_ids` already uses. Verified against the real database.

### P2-3: Add the live/network integration suite to CI (at least on a schedule)

- **Problem:** `.github/workflows/ci.yml` only runs the offline suite (`make test`, which
  deselects `network`-marked tests). The Sleeper/league live-integration claims in this project's
  docs depend on someone running them manually (as this session did, more than once), not an
  automated gate. **Still open** — not attempted this pass since it requires provisioning real API
  credentials as GitHub Actions secrets, a decision for the user.
- **Dependencies:** None technically, but requires the user's credential-ownership decision.
- **Recommended sequencing:** Propose to the user first. Once approved, add a separate scheduled
  workflow (not on every PR, since it hits real external services) running `pytest -m network`.
- **Acceptance criteria:** A scheduled CI job runs the live suite and fails visibly if a real
  source breaks; failures are distinguishable from PR-blocking failures.

---

## P3 — Low risk, do opportunistically

### ~~P3-1: Refresh CLAUDE.md's stale data-source-status note~~ — CLOSED (D50)

- CLAUDE.md's `## Data` section cited only D3 (the original 2026-08-20 probe) and described
  Sleeper/FantasyPros/CFBD as policy-blocked. Re-verified live with a fresh `alpha-squad sources
  status` run before editing — all three report `AVAILABLE` — and rewrote the note to match
  `docs/DATA_SOURCES.md`'s current narrative, citing D31/D36-D38. Only KeepTradeCut and ESPN
  remain unreachable, neither required by PRODUCT_SPEC.md's core outputs.

### ~~P3-2: Add expert-accuracy weighting to market-signal blending~~ — CLOSED/LIMITED (D51)

- Measured rather than assumed: re-confirmed live that even the paid FantasyPros API exposes only
  consensus statistics, never per-expert identity, so true per-expert weighting is genuinely
  unbuildable with data this project can access. The coarser proxy the real data does permit
  (`ecr_best`/`ecr_worst` expert-agreement dispersion) was measured against 1,925 real
  player-seasons (2022-2025) and found to have no consistent relationship with market accuracy —
  it reverses sign between rank tiers. Applied this project's own D39 standard (measure, and if
  the signal doesn't hold up, say so rather than force it in): **not adopted.** No change to
  `edge.py`'s gating logic. See D51 for the full methodology and numbers.

### ~~P3-3: Add an explicit in-season/ROS re-projection loop, if genuinely absent~~ — CLOSED (D46)

- Investigated rather than assumed: the pipeline existed (`weekly_projection_snapshot` +
  `projection_deltas`) but had never been run against real data in this deployment and nothing
  served it. See P2-1 above — same fix, same D-number, closed together.

---

## Notes on sequencing across what's left

- All four "built but invisible" capabilities identified at the start of this hardening pass
  (waiver/trade/roster-need/simulation) are now closed (D44/D48/D49), the pure-documentation item
  (P3-1) is closed (D50), and P3-2 has been measured and honestly resolved as LIMITED (D51) rather
  than left simply "not done." The only item left in this file is **P2-3** (network suite in CI),
  which needs a user credential decision — propose it rather than doing it unilaterally.
- **P0-1** requires no further code work — the repo-side decision is settled (D35/D42). The only
  open thread is a conversation with the user about provider-side key rotation status, not
  something to schedule as engineering work.
- **Note (2026-08-25):** a separate, later phase (M15, `docs/DECISIONS.md` D53) productized the
  intelligence this backlog hardened — real Sleeper league onboarding, My Team/Action Center/
  Player Detail/Draft/multi-asset Trade views — and found/fixed 6 further real bugs the same way
  this pass did (exercising the real app with Playwright, not code review). It is a separate body
  of work from the P0-P3 items above, not a continuation of this file's backlog; see D53 and
  `docs/PROJECT_STATE.md`'s M15 section for the full account. P2-3 (network suite in CI) remains
  the only item in *this* file still open from that pass.
- **Note (2026-08-26):** a further phase (M16, D54) empirically evaluated the productized
  system against strong baselines rather than assuming it was good because it ran, and found a
  new, real, well-evidenced gap: **P1-0** above, the draft recommender's roster-balance bug.
  This is now the highest-value item in this file — more concrete and more actionable than
  P2-3, since its root cause and acceptance test are already established by the evaluation
  harness itself. See `docs/DECISIONS.md` D54 and `docs/ALPHA_VS_BASELINES_EVALUATION.md` for
  the full evidence.
