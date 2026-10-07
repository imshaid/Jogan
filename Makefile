# Jogan developer commands. Run `make help` to list them.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
PROFILE ?= dev
SEED ?= 0

.PHONY: help setup lint format test check data history baselines forecast eval sizing impact docs stress bundle api run test-db clean

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

test-db: ## Apply the Supabase migrations to a throwaway Postgres and check RLS and audit (Docker)
	bash scripts/test-db.sh

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

sizing: ## Size the problem nationally from Bangladesh Bank figures → artifacts/sizing.json
	$(UV) run python -m jogan.eval.sizing

impact: ## Copy the impact page's numbers from artifacts/metrics.json → web/lib/impact.json
	$(UV) run python -m jogan.eval.web

docs: ## Write the numbers blocks in README.md, docs/ and report/ from artifacts/*.json
	$(UV) run python -m jogan.eval.docs

stress: ## Time Jogan's mornings for 10,000 agents → artifacts/stress.json (timing only)
	$(UV) run python -m jogan.eval.stress

bundle: ## Build the served demo bundle → bundle/ (PROFILE=full SEED=42 for the deployed one)
	$(UV) run python -m jogan.api.bundle --profile $(PROFILE) --seed $(SEED) --out bundle

api: ## Run the API locally on :8000 with the in-memory store (after make bundle)
	JOGAN_STORE=memory JOGAN_ENV=development JOGAN_CORS_ORIGINS=http://localhost:3000 \
		$(UV) run uvicorn --factory jogan.api.app:from_env --reload --port 8000

run: ## Run the API and the web app locally, no accounts needed (builds bundle/ if missing)
	UV=$(UV) bash scripts/run-local.sh

clean: ## Remove caches and build outputs
	rm -rf .pytest_cache .ruff_cache build dist
	find . -path ./.venv -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
