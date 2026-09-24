#!/usr/bin/env bash
# =============================================================================
# scripts/setup.sh - One-shot local setup (Linux / macOS / WSL)
#   1. finds Python >= 3.10        4. seeds the local SQLite database
#   2. creates .venv               5. runs the unit test suite
#   3. installs the package (-e) with dev extras + pre-commit hooks
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        PYTHON_CMD="$cmd"; break
    fi
done
[ -n "$PYTHON_CMD" ] || { echo "[ERROR] Python 3.10+ not found."; exit 1; }
echo "[OK] Python: $($PYTHON_CMD --version)"

[ -f .env ] || { cp .env.example .env && echo "[INFO] .env created from .env.example"; }

[ -x .venv/bin/python ] || { echo "[1/4] Creating .venv"; "$PYTHON_CMD" -m venv .venv; }
VENV_PY=.venv/bin/python

echo "[2/4] Installing package with dev extras"
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -e ".[dev]"
"$VENV_PY" -m pre_commit install >/dev/null 2>&1 || true

echo "[3/4] Seeding local database"
"$VENV_PY" -m logistics_tower.db.seed

echo "[4/4] Running unit tests"
"$VENV_PY" -m pytest -m "not integration" -q

echo
echo "Done. Start the dashboard with: ./scripts/run.sh   (or: make run)"
