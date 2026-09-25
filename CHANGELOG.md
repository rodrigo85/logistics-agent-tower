# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.4.0] - 2026-09-25

### Added
- **Delivery dates.** Every order has a `delivery_date`; the WMS keeps a rolling horizon of `PLANNING_HORIZON_DAYS` (3) days and "Gerar pedidos" fills all of them (40 orders per day). The seed regenerates itself when today has no orders.
- Planning per day: `POST /dispatch/plan` takes `plan_date`; the dashboard has date tabs (hoje / amanhã / day after) with order counts and plan status; `/api/dashboard-data?date=` and `/api/orders/generate?days=`.
- Copilot understands dates in the operator's words ("hoje", "amanhã", "quinta", "27/09", ISO): every operator tool takes a `date`; new `move_customer_orders` tool ("passa o Koch de Gravatá para amanhã"); the copilot re-plans every day it touched (origin and destination when moving).
- `logistics_tower.dates` (tolerant date parser, horizon, labels) with tests; `REFERENCE_DATE` setting to freeze "today" for demos.
- Eval cases for dates (move to tomorrow, skip tomorrow, question about tomorrow).

### Changed
- Repository, WMS, planner cache and manifests are date-scoped; `GET /api/vehicle/{plate}/itinerary` reads the most recently planned day.

## [1.3.0] - 2026-09-25

### Added
- **Dispatcher Copilot**: conversational LLM agent (LangGraph tool-calling loop) that applies operator instructions to today's plan and re-plans: "não vamos atender X hoje" (skip), "X agendou recebimento entre 9 e 11" (reschedule window, remembered for future orders), restore, questions about the plan and standing notes. Exposed as `POST /copilot/chat`, `GET /copilot/status`, a chat panel in the dashboard and the `logistics-tower-chat` CLI (ADR-0007).
- LLM provider factory (`llm/provider.py`): Ollama (default), Gemini and OpenAI behind optional extras, with a diagnostics endpoint that never exposes secrets.
- Operator tools registered in MCP (in-process and stdio server): `find_customers`, `skip_customer_today`, `restore_customer_today`, `reschedule_customer_window`, `list_orders`, `remember_note`.
- Long-term memory: `operator_memory` table, customer window overrides honoured by the order factory, customer rules written from the chat.
- `GET /agents` registry (planning agents, copilot, MCP tools, latest plan) as a lifecycle view.
- Evaluation harness `evals/run_evals.py` + `evals/cases.jsonl` scoring tool/entity/replan accuracy and latency per provider; `make eval`; `docs/LLM_EVALUATION.md`.
- Tests with a scripted tool-calling model covering skip, reschedule, restore, ambiguity, memory, the API and the MCP server tool listing through the official SDK.

### Changed
- Order status gains `SKIPPED` (+ `skip_reason`); re-planning only brings `DISPATCHED` orders back, so skipped customers stay out until restored.
- Dispatch planning extracted to `services/dispatch_service.py` (shared by API, CLI and copilot); the latest-plan cache now also carries unallocated orders, warnings and the thread id.
- `/api/dashboard-data` exposes skipped orders and the latest plan status.

## [1.2.0] - 2026-09-24

### Changed
- **Business model:** cold-chain distribution to food retailers. The fleet is now five refrigerated trucks and every order is refrigerated (chilled or frozen).
- **One multi-stop route per vehicle per day** replaces dedicated FTL trips: loading at 05:00, departure at 06:00, up to `MAX_STOPS_PER_VEHICLE` (12) stops, 20-minute service per stop, lunch after the first stop completed at or after 11:30, 11-hour shift limit (ADR-0006).
- Allocation uses a two-pass geographic sweep (polar angle around the CD) followed by centroid refinement so nearby customers share a truck; sequencing inside each route is an OR-Tools TSP with time windows (hard lower / soft upper bounds). On the seed dataset: 387 km planned vs 604 km with a plain sweep.
- Customer pool rebuilt with 56 supermarkets, wholesalers, grocery stores, mini-markets, bakeries, butchers, fishmongers, greengrocers and convenience stores across Itajaí, Balneário Camboriú, Camboriú, Navegantes, Penha, Piçarras and Brusque, each with segment, dock type and access rules.
- Order generation moved to `db/order_factory.py` (per-segment weight, volume, value, windows, temperature regime); the seed produces 40 deterministic orders and `POST /api/orders/generate` defaults to 40 (capped by the pool size).
- Dashboard rewritten for single-route itineraries: route summary chips, load bars per truck, stop-by-stop timeline with lunch and shift-end status.
- Risk agent now also flags `SHIFT_LIMIT` and `UNALLOCATED` (both require human approval).

### Added
- `segment` on customers and `temperature_regime` on orders; automatic local database rebuild on schema drift.
- `scripts/export_samples.py` to regenerate `data/samples/*.json` from the seed definitions.
- Tests for sweep clustering, VUC-only constraints, max stops, TSPTW sequencing, waiting for windows, lunch placement and the auto-approve path.

### Removed
- Trip-based fields (`trips`, `trip_number`) from loads, routes and the dashboard.

## [1.1.0] - 2026-09-24

### Added
- Google Maps Routes API v2 integration with live traffic and polyline geometry (`services/traffic_service.py`), optional via `GOOGLE_MAPS_API_KEY`.
- Dynamic order generation with a regional address pool (Itajaí, Balneário Camboriú, Navegantes, Camboriú, Brusque).
- Per-vehicle daily itinerary endpoint (`GET /api/vehicle/{plate}/itinerary`).
- GitHub Actions CI: ruff, mypy, pytest matrix (Ubuntu/Windows x Python 3.10/3.12), Docker build, Terraform validate.
- Pre-commit hooks, `Makefile`, `.editorconfig`, `.gitattributes`, `.dockerignore`, Dependabot, issue and PR templates.
- `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`, `docs/ARCHITECTURE.md` and five ADRs.
- `logistics-tower-seed` console script and `logistics_tower.logging_setup`.
- Multi-stage, non-root Docker image with health check; `api` service in `docker-compose.yml`.

### Changed
- API split into an application factory (`api/app.py`) and routers per bounded context (`api/routers/`).
- Database seeding moved from service constructors to application entry points (API lifespan, CLI, MCP server).
- `DATABASE_URL` is now a first-class setting (`Settings.database_url`); tests run against a temporary SQLite file.
- Version is read from package metadata (`importlib.metadata`) instead of being hard-coded in three places.
- Launch scripts moved to `scripts/` and simplified (editable install instead of a `.pth` hack).
- `httpx` promoted to a runtime dependency; new `postgres` extra with `psycopg`.
- Ruff rule set expanded (isort, pyupgrade, bugbear, simplify, perf); code base modernised to PEP 585/604 typing.

### Fixed
- Non-deterministic customer codes generated with `hash()` (now SHA-256 based).
- Naive `datetime.utcnow()` usage replaced by timezone-aware timestamps.
- Stale default `cd_id` (`CD-SP01-CAJAMAR`) in API schema and fleet agent.
- Tests no longer require a real Google Maps key or network access; live calls are opt-in via the `integration` marker.
- Subpackages lacked `__init__.py`, which broke wheel builds.

### Removed
- `data/logistics.db` from version control (generated on first run).
- `requirements.txt` (single source of truth is `pyproject.toml`).

## [1.0.0] - 2026-09-20

### Added
- Initial release: LangGraph multi-agent DAG (supervisor, fleet, routing, risk) with Human-in-the-Loop gate.
- Google OR-Tools CVRPTW solver, dedicated FTL multi-trip allocation, SQLAlchemy 2.0 persistence.
- FastAPI REST API, interactive Leaflet dashboard, Rich CLI, MCP server and client.
- Terraform for GCP (Cloud Run, Cloud SQL, Artifact Registry, BigQuery, Secret Manager).

[Unreleased]: https://github.com/rodrigo85/logistics-agent-tower/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/rodrigo85/logistics-agent-tower/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/rodrigo85/logistics-agent-tower/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/rodrigo85/logistics-agent-tower/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/rodrigo85/logistics-agent-tower/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/rodrigo85/logistics-agent-tower/releases/tag/v1.0.0
