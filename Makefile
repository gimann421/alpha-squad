.PHONY: install test test-network test-cov lint fmt check-secrets ingest identity college-usage features market train evaluate edge simulate orchestrate serve serve-web clean

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

features:
	uv run alpha-squad features build --season-start 2015 --season-end 2025

market:
	uv run alpha-squad market build
	uv run alpha-squad market build-dynasty-values

train:
	uv run alpha-squad train established-season
	uv run alpha-squad train uncertainty
	uv run alpha-squad train rookie

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
