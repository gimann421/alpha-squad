.PHONY: install test test-network test-cov lint fmt check-secrets ingest identity college-usage features team-scores market train project-current-season capture-live-market evaluate edge simulate orchestrate serve serve-web clean

install:
	uv sync --extra dev
	uv pip install -e . --reinstall-package alpha-squad

test:
	uv run pytest

test-network:
	uv run pytest -m network

test-cov:
	uv run pytest --cov=alpha_squad --cov-report=term-missing

# D35: a real API key was once committed directly to .env.example. check-secrets fails the
# build if any tracked *.env.example file has a non-empty secret-shaped value again.
check-secrets:
	uv run python scripts/check_no_secrets.py

lint: check-secrets
	uv run ruff check src tests
	uv run ruff format --check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

# Full pipeline, in dependency order. Each target is also independently re-runnable
# (every builder is an idempotent upsert against stored snapshots/already-built tables) --
# see docs/DATA_SOURCES.md for the season range this was actually built and tested against
# (2015-2025) and which sources are AVAILABLE vs BLOCKED_BY_POLICY.
ingest:
	uv run alpha-squad sources ingest --season-start 2015 --season-end 2025

identity:
	uv run alpha-squad identity build

# Must run BETWEEN identity and features: it needs player_id_map's espn_id bridge, and
# `features build` is what joins college_usage into rookie_features. Running it after
# `features` instead leaves rookie_features.college_usage_* NULL, which models/rookie/data.py
# silently imputes to 0.0 -- i.e. the rookie model trains on zeroed college features with no
# warning. Requires CFBD_API_KEY (docs/DECISIONS.md D38).
college-usage:
	uv run alpha-squad features build-college-usage

# `features build` now builds team_week_points itself, BEFORE the K/DST step that depends on
# it (D78). Until then this target ran before `team-scores`, so on a clean database the DST
# scoring step found an empty team_week_points, wrote zero rows, and a league starting a DEF
# got an empty slot with nothing on screen saying so.
features:
	uv run alpha-squad features build --season-start 2015 --season-end 2025

# team_week_points (real final scores, from pbp) is a separate table from `features`'s
# team_week_stats -- simulate_team_season's environment draw needs both. `features build`
# already builds it (see above); this target stays for refreshing it on its own.
team-scores:
	uv run alpha-squad features build-team-scores --season-start 2015 --season-end 2025

market:
	uv run alpha-squad market build
	uv run alpha-squad market build-dynasty-values

train:
	uv run alpha-squad train established-season
	uv run alpha-squad train uncertainty
	uv run alpha-squad train rookie

# ------------------------------------------------------------------------------------------
# Current-season projections (D78). Everything above this line is HISTORICAL: `train` is a
# walk-forward backtest over seasons whose outcomes are already known, and it deliberately
# writes nothing for the upcoming season. This target is what produces the board an actual
# draft is run against.
#
# CURRENT_SEASON is the season being DRAFTED FOR -- the one that has not been played. Override
# it (`make project-current-season CURRENT_SEASON=2027`) rather than editing it here.
#
# It ends on `train projection-status`, which is a gate, not a summary: it calls the same
# `load_season_projections` the draft engine calls and exits non-zero if the board it gets
# back is missing, empty, or missing a position the league has to start. A pipeline that
# merely exits 0 does not establish that the application has projections.
CURRENT_SEASON ?= 2026

project-current-season:
	uv run alpha-squad sources ingest --season-start $(CURRENT_SEASON) --season-end $(CURRENT_SEASON)
	uv run alpha-squad identity build
	uv run alpha-squad market build
	uv run alpha-squad train uncertainty-project --season $(CURRENT_SEASON)
	uv run alpha-squad train rookie-project --draft-class $(CURRENT_SEASON)
	uv run alpha-squad train kdst-projections --season-start $(CURRENT_SEASON) --season-end $(CURRENT_SEASON)
	uv run alpha-squad train projection-status --season $(CURRENT_SEASON)

# Optional: today's FantasyPros consensus straight from the live API, as its own
# provenance-tagged series (source='fantasypros_live') alongside the DynastyProcess-sourced
# board. Requires FANTASYPROS_API_KEY. Not part of the target above because the board that
# every historical measurement was made against is the DynastyProcess one, and a draft should
# be run against the same series the model was validated on.
capture-live-market:
	uv run alpha-squad market capture-live-fantasypros --season $(CURRENT_SEASON)

evaluate:
	uv run alpha-squad evaluate baselines

edge:
	uv run alpha-squad edge build
	uv run alpha-squad edge validate

simulate:
	uv run alpha-squad simulate team-season --team KC --season 2024

orchestrate:
	uv run alpha-squad orchestrate demo

serve:
	uv run uvicorn alpha_squad.api.app:app --reload --port 8000

serve-web:
	cd web && npm run dev

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
