#!/usr/bin/env bash
# scripts/run.sh - Start the API + dashboard with auto-reload (Linux / macOS / WSL)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { echo "[ERROR] .venv not found. Run ./scripts/setup.sh first."; exit 1; }
echo "Logistics Agent Tower -> http://localhost:8000  (Swagger: /docs)"
exec .venv/bin/python -m uvicorn logistics_tower.api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src
