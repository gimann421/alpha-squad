.PHONY: install test test-network test-cov lint fmt ingest identity features train evaluate edge serve serve-web clean

install:
	uv sync --extra dev
	uv pip install -e . --reinstall-package alpha-squad

test:
	uv run pytest

test-network:
	uv run pytest -m network

test-cov:
	uv run pytest --cov=alpha_squad --cov-report=term-missing

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

ingest:
	uv run alpha-squad sources ingest

identity:
	uv run alpha-squad identity build

features:
	uv run alpha-squad features build

train:
	uv run alpha-squad train --walk-forward

evaluate:
	uv run alpha-squad evaluate --compare-baselines

edge:
	uv run alpha-squad edge build

serve:
	uv run uvicorn alpha_squad.api.app:app --reload --port 8000

serve-web:
	cd web && npm run dev

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
