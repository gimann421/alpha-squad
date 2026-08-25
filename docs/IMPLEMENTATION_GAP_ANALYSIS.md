# Alpha Squad — Implementation Gap Analysis

Companion to `docs/CURRENT_STATE_AUDIT.md`. Originally written 2026-08-24 (commit `e0ca6c3`);
refreshed 2026-08-25 after a P0-P2/P4/P5/P7/P8 hardening pass (`docs/DECISIONS.md` D41-D48) closed
most of the original list. Each item still reflects what is **actually missing today** — not a
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

### P3-2: Add expert-accuracy weighting to market-signal blending

- **Problem:** PRODUCT_SPEC.md calls for "expert weighting uses demonstrated accuracy where data
  permits"; no such logic exists in `market/` today. **Still open.**
- **Dependencies:** Benefits from the EDGE backtest artifact existing first (now true, D41), since
  expert accuracy is itself a historical-performance measurement.
- **Acceptance criteria:** Market blending demonstrably weights a source differently based on a
  measured historical-accuracy statistic for that source, not a fixed constant.

### ~~P3-3: Add an explicit in-season/ROS re-projection loop, if genuinely absent~~ — CLOSED (D46)

- Investigated rather than assumed: the pipeline existed (`weekly_projection_snapshot` +
  `projection_deltas`) but had never been run against real data in this deployment and nothing
  served it. See P2-1 above — same fix, same D-number, closed together.

---

## Notes on sequencing across what's left

- All four "built but invisible" capabilities identified at the start of this hardening pass
  (waiver/trade/roster-need/simulation) are now closed (D44/D48/D49), and the one pure-
  documentation item (P3-1) is closed too (D50). What remains is **P2-3** (network suite in CI,
  needs a user credential decision — propose it rather than doing it unilaterally) and **P3-2**
  (expert-accuracy weighting, real modeling work but no user decision needed) — both genuinely
  low-risk, low-urgency, and can be done in either order.
- **P0-1** requires no further code work — the repo-side decision is settled (D35/D42). The only
  open thread is a conversation with the user about provider-side key rotation status, not
  something to schedule as engineering work.
