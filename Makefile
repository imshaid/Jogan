# Jogan developer commands. Run `make help` to list them.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
PROFILE ?= dev
SEED ?= 0

.PHONY: help setup lint format test check data history baselines forecast eval clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install Python deps with uv and the git hooks
	$(UV) sync
	$(UV) run pre-commit install

lint: ## Lint and check formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Auto-format and apply safe lint fixes
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

test: ## Run the test suite
	$(UV) run pytest

check: lint test ## Lint and tests (same as CI)

data: ## Generate a simulated world into data/ (PROFILE=tiny|dev|full|stress, SEED=0)
	$(UV) run python -m jogan.sim --profile $(PROFILE) --seed $(SEED)

history: ## Run the status quo and write its observation log (PROFILE, SEED)
	$(UV) run python -m jogan.ops --profile $(PROFILE) --seed $(SEED) --write

baselines: ## Compare every baseline policy on one world (PROFILE, SEED)
	$(UV) run python -m jogan.ops --profile $(PROFILE) --seed $(SEED) --policy all

forecast: ## Backtest the drain forecast on the status-quo log (PROFILE, SEED; after history)
	$(UV) run python -m jogan.forecast --profile $(PROFILE) --seed $(SEED)

eval: ## Final policy comparison over the evaluation seeds → artifacts/metrics.json (ARGS for dev runs)
	$(UV) run python -m jogan.eval $(ARGS)

clean: ## Remove caches and build outputs
	rm -rf .pytest_cache .ruff_cache build dist
	find . -path ./.venv -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
