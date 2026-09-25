# Developer entry points. Works on Linux/macOS/WSL and on Windows with GNU make (Git Bash / choco install make).
# Windows users without make can use the launchers in scripts/.

PYTHON ?= python
VENV   ?= .venv
ifeq ($(OS),Windows_NT)
	VENV_PY := $(VENV)/Scripts/python.exe
else
	VENV_PY := $(VENV)/bin/python
endif

.DEFAULT_GOAL := help

.PHONY: help venv install seed run cli chat mcp test test-all cov eval lint format typecheck check clean docker-build docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create the virtual environment
	$(PYTHON) -m venv $(VENV)

install: ## Install the package in editable mode with dev extras + pre-commit hooks
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -e ".[dev,mcp,ollama]"
	$(VENV_PY) -m pre_commit install || true

seed: ## Reset and seed the local database
	$(VENV_PY) -m logistics_tower.db.seed

run: ## Start the API + dashboard with auto-reload
	$(VENV_PY) -m uvicorn logistics_tower.api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src

cli: ## Run the interactive terminal dispatcher
	$(VENV_PY) -m logistics_tower.cli

chat: ## Talk to the Dispatcher Copilot in the terminal (needs an LLM provider)
	$(VENV_PY) -m logistics_tower.chat_cli

mcp: ## Run the MCP server over stdio
	$(VENV_PY) -m logistics_tower.mcp.server

test: ## Run unit tests (external integrations skipped)
	$(VENV_PY) -m pytest -m "not integration"

test-all: ## Run every test, including Google Maps integration (needs GOOGLE_MAPS_API_KEY)
	$(VENV_PY) -m pytest

eval: ## Evaluate the copilot against the configured LLM provider (see docs/LLM_EVALUATION.md)
	$(VENV_PY) evals/run_evals.py --provider $${LLM_PROVIDER:-ollama}

cov: ## Run tests with coverage report
	$(VENV_PY) -m pytest -m "not integration" --cov --cov-report=term-missing --cov-report=xml

lint: ## Lint with ruff
	$(VENV_PY) -m ruff check src tests evals

format: ## Auto-format and auto-fix with ruff
	$(VENV_PY) -m ruff check --fix src tests evals
	$(VENV_PY) -m ruff format src tests evals

typecheck: ## Static type check with mypy
	$(VENV_PY) -m mypy

check: lint typecheck test ## Everything CI runs

clean: ## Remove caches and build artifacts
	rm -rf build dist .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

docker-build: ## Build the API image
	docker build -f docker/Dockerfile -t logistics-agent-tower:local .

docker-up: ## Start PostgreSQL + Adminer + API
	docker compose up -d --build

docker-down: ## Stop the compose stack
	docker compose down
