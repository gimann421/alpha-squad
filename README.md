# Alpha Squad — Fantasy Football Market-Inefficiency Intelligence

Alpha Squad projects fantasy football player performance, quantifies uncertainty, compares
model output against market consensus (EDGE), and turns that into league-specific draft/waiver/
trade decisions — for a real 10-team, 2QB/2RB/2WR/1TE/2FLEX dynasty PPR league by default,
configurable to others. See `PRODUCT_SPEC.md` and `ARCHITECTURE.md` for the full product/system
design, and `docs/DECISIONS.md` for why specific implementation choices were made.

## Requirements

- Python 3.12 (pinned in `.python-version`) via [`uv`](https://docs.astral.sh/uv/)
- Node 18+ (for the `web/` frontend, optional unless you're running the SPA)

## Setup

```bash
make install     # uv sync --extra dev, editable install
make lint         # ruff check + format --check
make test         # offline unit/leakage/contract tests (network tests deselected)
make test-network # tests that hit real sources (nflverse, DynastyProcess, ...)
```

`data/`, `models/`, `predictions/`, `reports/`, and `state/` are gitignored and fully
reproducible from the pipeline below — nothing under them is ever committed. `pytest`
deselects the `network` marker by default so the offline suite runs fast with no external
calls; `tests/fixtures/` holds schema-accurate synthetic data, not real source data.

## Running the full pipeline

Each step is an idempotent upsert against already-stored snapshots/tables, so any step can be
re-run on its own once its dependencies have run at least once.

```bash
make ingest        # fetch + snapshot every reachable source (2015-2025 by default)
make identity      # build the canonical player_id spine + crosswalk
make college-usage # CFBD college production, espn_id-bridged (needs CFBD_API_KEY) -- must run
                   # BEFORE `features`, which is what joins it into rookie_features
make features      # as-of feature store: games, player/team week stats, engineered features,
                   # real final team scores, and K/DST scoring (which depends on them)
make team-scores  # refresh team_week_points alone (`make features` already builds it)
make market      # FantasyPros ECR (via DynastyProcess) + dynasty market values
make train       # walk-forward established-player ML, uncertainty/calibration, rookie models
                 # -- a BACKTEST over already-played seasons; it writes nothing for the
                 # upcoming season (see "Projecting the upcoming season" below)
make evaluate    # baseline evaluation report (reports/baseline_evaluation.md)
make edge        # model-vs-market EDGE + historical EDGE validation
make simulate    # correlated team-season Monte Carlo (one example team/season)
make orchestrate # run a real task DAG through the agent orchestrator
make serve       # FastAPI backend on :8000
make serve-web   # React/Vite SPA on :5173 (set VITE_API_BASE_URL, see web/.env.example)
```

## Projecting the upcoming season

Everything above is historical. `make train` walk-forward evaluates seasons whose outcomes are
already known and deliberately writes nothing for the season you are about to draft. The board a
real draft runs against comes from its own target:

```bash
make project-current-season                      # defaults to CURRENT_SEASON=2026
make project-current-season CURRENT_SEASON=2027  # override rather than editing the Makefile
```

It ingests the target season, rebuilds identity and the market board, then runs the three
forward-looking projection jobs — `train uncertainty-project` (established players),
`train rookie-project` (the incoming rookie class) and `train kdst-projections` (kickers and team
defenses) — and ends on a gate:

```bash
uv run alpha-squad train projection-status --season 2026
```

`projection-status` does not inspect the jobs' exit codes. It calls
`league/replacement.py::load_season_projections` — the exact function `recommend_draft_pick`, the
API and every evaluation path call — and exits non-zero if the board it gets back is missing,
empty, or missing a position the league has to start. It also reports any rows written for that
season under a superseded `model_version`, so a stale artifact cannot be mistaken for live output.
A pipeline that merely exits 0 does not establish that the application has projections; this does.

`make capture-live-market` additionally pulls today's FantasyPros consensus straight from the live
API as its own provenance-tagged series. It is deliberately not part of the target above: every
historical measurement was made against the DynastyProcess-sourced board, and a draft should run
against the series the model was validated on.

### Rehearsing a draft end to end

`web/draft-rehearsal.mjs` drives a real Chromium through a full manual draft against the real
API and the real current-season projections — pick numbers, correcting one, marking your own
pick, the roster staying synchronized, a fresh recommendation, undo, and a reload with
everything still correct afterward. Run it after any change to the draft path:

```bash
make serve      # FastAPI on :8000, in one shell
make serve-web  # Vite on :5173, in another
cd web && node draft-rehearsal.mjs
```

It has caught four real bugs that code review did not (D78), including the Draft view sitting on
last season while current-season projections existed. `CHROMIUM_PATH` overrides the browser
location.

`alpha-squad --help` (or `--help` on any subcommand) is the source of truth for every CLI
command and flag — the tree is `sources`, `identity`, `features`, `market`, `evaluate`,
`train`, `edge`, `evidence`, `league`, `orchestrate`, `simulate`.

Check real source reachability before assuming a step will work end to end:

```bash
uv run alpha-squad sources status
```

`docs/DATA_SOURCES.md` records which sources are AVAILABLE vs. `BLOCKED_BY_POLICY` in this
environment and why (adapters for blocked sources are fully implemented and activate
unchanged if the policy or credentials change — they never return fabricated data).

## Project structure

```
src/alpha_squad/
  config/     settings, league YAML configs
  sources/    one adapter per external data provider (+ snapshot registry)
  identity/   canonical player_id spine, crosswalk, ambiguity queue
  features/   as-of feature store (leakage-safe by construction)
  models/     baselines, established-player ML, rookie ML, uncertainty, simulation
  market/     consensus (ECR/dynasty value), EDGE (model vs. market)
  evidence/   structured evidence events, bounded prior-update
  league/     replacement level, scarcity, draft/waiver/trade recommendations
  agents/     typed task/result contracts, DAG orchestrator, disagreement protocol
  api/        FastAPI app (pure projection layer over the tables/functions above)
  cli.py      Typer CLI — the primary way to drive every module above
web/          React + Vite + TS SPA (presentation only, no business logic)
tests/        unit/ integration/ leakage/ contracts/ e2e/ fixtures/
docs/         DATA_SOURCES.md, DECISIONS.md, PROJECT_STATE.md, TRACEABILITY.md
```

## Documentation map

- `PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `ACCEPTANCE_CRITERIA.md`,
  `AGENT_CONTRACTS.md` — the approved product/system design this implementation follows.
- `docs/DECISIONS.md` — append-only log of every non-obvious implementation decision,
  assumption, and bug found/fixed, with reasoning (read this before assuming something is a
  bug rather than a documented tradeoff).
- `docs/DATA_SOURCES.md` — verified, current reachability status of every data source.
- `docs/PROJECT_STATE.md` — milestone-by-milestone status.
- `docs/TRACEABILITY.md` — every `ACCEPTANCE_CRITERIA.md` checkbox mapped to the module/test/
  report that satisfies it, or explicitly marked BLOCKED/LIMITED with reason and fallback.
- `reports/` (gitignored, regenerated by the commands above) — baseline/model evaluation,
  EDGE validation, calibration diagnostics.

## Original planning package

The original autonomous-build planning documents (`CLAUDE_CODE_LEAD_PROMPT.md`, and
`PRODUCT_SPEC.md`/`ARCHITECTURE.md`/etc. listed above) remain in the repository as the
authoritative product/process requirements this codebase was built against; they describe the
planning package this system was built from, not the system's own setup or usage.
