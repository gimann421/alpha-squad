# Alpha Squad — Implementation Gap Analysis

Companion to `docs/CURRENT_STATE_AUDIT.md` (2026-08-24, commit `e0ca6c3`). Each item below reflects
what is **actually missing today**, per that audit — not a re-statement of the original spec. Items
are ordered P0 (do first / highest risk) → P3 (nice-to-have / low risk). "Dependencies" lists other
items in this file that should land first; items with no listed dependency can start immediately.

---

## P0 — Do first

### P0-1: Resolve the leaked-credential Git-history exposure
- **Problem:** Real API key values from the D35 incident (`docs/DECISIONS.md`) remain permanently
  retrievable via `git log --all -p -- .env.example` on a repo with a public-facing remote
  (`github.com/gimann421/alpha-squad`). Fixed forward, never purged from history.
- **Dependencies:** None. Should happen before any other work that touches this repo's remote state.
- **Recommended sequencing:**
  1. Confirm with the user whether the leaked keys are still active; rotate at the provider if so
     (independent of any Git action).
  2. Decide, with the user's explicit sign-off, whether to rewrite Git history (`git filter-repo` or
     equivalent) to purge the leaked commits — this is a destructive, irreversible, shared-history
     action and must not be done unilaterally by an autonomous session.
  3. If history is rewritten: force-push is required and every existing clone/PR becomes stale — plan
     the timing with the user.
  4. If history is *not* rewritten (e.g. because rotation makes the exposure moot): document that
     decision explicitly in `docs/DECISIONS.md` as a closed item, with the reasoning.
- **Acceptance criteria:** Either (a) the leaked key values no longer appear anywhere in
  `git log --all -p`, and a fresh clone confirms it, or (b) `docs/DECISIONS.md` records an explicit,
  reasoned decision not to rewrite history (e.g., keys already rotated and confirmed dead), signed
  off by the user. No autonomous session should mark this "done" via history rewrite without that
  sign-off.

---

## P1 — High value, ready to build

### P1-1: Wire waiver, trade, and roster-need recommendations into the web UI
- **Problem:** `waiver.py`, `trade.py`, and roster-fit logic are real, tested, and live-verified
  server-side, but no reachable UI view calls them (§20 of the audit). This is the largest gap
  between what the spec promises and what a user can actually do today.
- **Dependencies:** None — purely additive frontend work against existing, working API endpoints.
- **Recommended sequencing:** Add a Waiver tab (mirror the existing League tab's data-loading
  pattern in `web/src/components/`), then a Trade evaluation view, then surface roster-need directly
  in the existing League tab (it already loads `LeagueContext`, which is a roster-need input).
- **Acceptance criteria:** From the running app, a user can (1) get a real FAAB bid recommendation
  for a real Sleeper league without touching the API directly, (2) get a real dynasty trade
  evaluation the same way, (3) see roster-need reflected somewhere in the League view. Playwright (or
  manual) verification against the real app, not just an API call, per this project's UI-testing
  standard.

### P1-2: Commit an EDGE historical-backtest report artifact
- **Problem:** A historical EDGE backtest was run with genuine mixed results (per the audit's EDGE
  sub-finding), but no `reports/` file preserves it — the "historical EDGE performance is evaluated"
  acceptance criterion currently rests on trust, not a reviewable document.
- **Dependencies:** None.
- **Recommended sequencing:** Re-run the existing backtest logic (do not re-derive it from scratch —
  find whatever produced the sub-audit's "genuine mixed results" claim first), write
  `reports/edge_backtest.md` following the same format as `reports/calibration_report.md` and
  `reports/baseline_evaluation.md`, and update `docs/TRACEABILITY.md` to point to it.
- **Acceptance criteria:** `reports/edge_backtest.md` exists, contains real per-position/per-season
  numbers (not aggregate-only), and is referenced from `docs/PROJECT_STATE.md`.

### P1-3: Add model-artifact persistence for production model versions
- **Problem:** No model is ever saved to disk; every prediction requires an in-process retrain. This
  breaks the "reproducible historical prediction" requirement at inference time (only the training
  *inputs* are reconstructable today) and means the API's serving path is really a training path.
- **Dependencies:** None, but touches `models/established/`, `models/rookie/`, `models/uncertainty/`,
  and whatever currently triggers training-before-serving in the API layer — read those paths fully
  before starting, since this is the largest code change in this backlog.
- **Recommended sequencing:** Start with the established-player model (highest-traffic path): add a
  `save_model`/load path keyed by `model_version`, gated behind the existing `model_registry` table
  (a version only becomes "servable" once evaluation has run and passed). Extend to rookie and
  uncertainty models once the established path is proven. Keep `models/` gitignored per CLAUDE.md —
  this is a runtime artifact, not something to commit.
- **Acceptance criteria:** The API can serve a prediction for a given `model_version` without
  retraining in that request; a regression test proves a served prediction matches what training
  produced for the same inputs; `docs/DECISIONS.md` records the decision with a D-number.

---

## P2 — Real gaps, lower urgency

### P2-1: Feed evidence-adjusted projections into what's actually served
- **Problem:** The bounded (±15%) evidence-adjustment function is correctly implemented but unused
  except as an EDGE veto input — it does not affect the served projection or ranking.
- **Dependencies:** None, but should be sequenced after P1-3 if that changes how projections are
  served, to avoid rework.
- **Recommended sequencing:** Decide explicitly (with the user, since this changes what "the
  projection" means) whether evidence should adjust the served projection directly, or whether the
  current "evidence only vetoes EDGE" design is intentional and should instead be documented as such
  in PRODUCT_SPEC.md. Either resolution is acceptable; leaving it silently unused is not.
- **Acceptance criteria:** Either evidence-adjusted values are demonstrably reflected in a served
  projection (with a test proving it), or `docs/DECISIONS.md` records an explicit decision that
  evidence is EDGE-veto-only by design, with reasoning.

### P2-2: Implement future-draft-pick valuation in the trade engine
- **Problem:** `LeagueContext.future_picks` is loaded but never read by `trade.py::recommend_dynasty_trade`
  — no future-pick valuation logic exists anywhere in `league/`.
- **Dependencies:** None.
- **Recommended sequencing:** Add a pick-value curve (can start as a documented heuristic, consistent
  with the existing disclosed age-curve pattern in `trade.py`) keyed by round/pick-position, feed it
  into `recommend_dynasty_trade`'s existing value calculation, and extend the `reasons` output.
- **Acceptance criteria:** `recommend_dynasty_trade` accepts and uses `future_picks`; a test proves a
  trade including a future 1st materially changes the recommendation vs. an otherwise-identical trade
  without one.

### P2-3: Add the live/network integration suite to CI (at least on a schedule)
- **Problem:** `.github/workflows/ci.yml` only runs the offline suite (`make test`, which deselects
  `network`-marked tests). The Sleeper/league live-integration claims in this audit were only
  verified because I ran them manually this session — there is no automated gate on them.
- **Dependencies:** Requires provisioning real API credentials as GitHub Actions secrets — a decision
  for the user (credential ownership/rotation policy), not something to do unilaterally.
- **Recommended sequencing:** Propose to the user first (credentials need to live in GitHub secrets,
  which is outside this repo). Once approved, add a separate scheduled workflow (not on every PR,
  since it hits real external services) running `pytest -m network`.
- **Acceptance criteria:** A scheduled CI job runs the live suite and fails visibly if a real source
  breaks; failures are distinguishable from PR-blocking failures.

---

## P3 — Low risk, do opportunistically

### P3-1: Refresh CLAUDE.md's stale data-source-status note
- **Problem:** CLAUDE.md still describes Sleeper/FantasyPros/CFBD as blocked by egress policy; this
  was resolved by D36/D37 and re-confirmed live this audit.
- **Dependencies:** None.
- **Acceptance criteria:** CLAUDE.md's data section matches the current, audit-confirmed reality;
  the "re-verify with `alpha-squad sources status`" instruction stays (it's still good practice).

### P3-2: Add expert-accuracy weighting to market-signal blending
- **Problem:** PRODUCT_SPEC.md calls for "expert weighting uses demonstrated accuracy where data
  permits"; no such logic exists in `market/` today.
- **Dependencies:** Benefits from P1-2's backtest artifact existing first, since expert accuracy is
  itself a historical-performance measurement.
- **Acceptance criteria:** Market blending demonstrably weights a source differently based on a
  measured historical-accuracy statistic for that source, not a fixed constant.

### P3-3: Add an explicit in-season/ROS re-projection loop, if genuinely absent
- **Problem:** The audit marked this PARTIAL rather than confirming it doesn't exist — it needs a
  direct investigation before being treated as a real gap.
- **Dependencies:** None.
- **Recommended sequencing:** First re-verify whether this already exists (re-check `established/`'s
  training entry points for a within-season retraining or re-scoring path) before writing new code.
- **Acceptance criteria:** Either confirmed to already exist (update the audit's table), or built and
  tested following the same walk-forward discipline as the rest of the established-player pipeline.

---

## Notes on sequencing across the whole list

- P0-1 should not be blocked by anything else, but also should not be rushed into a unilateral
  history rewrite — it needs the user's explicit decision, which may take longer than the code work
  in P1/P2.
- P1-3 (model persistence) is the largest single change in this list and touches the most existing
  code; if a future session picks up this backlog, read `models/established/`, `models/rookie/`, and
  `models/uncertainty/` in full before starting, and add the regression test *before* changing serving
  behavior, per this project's standing "no hidden failing tests" / "add regression tests" rules.
- P1-1 (UI wiring) is the fastest way to make the existing, already-tested backend work valuable to
  an actual user, and has no risk of touching model-quality code — a good first pick for the next
  implementation session if the user wants quick, low-risk, high-visibility progress.
