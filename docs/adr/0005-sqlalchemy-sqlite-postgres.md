# ADR-0005: SQLAlchemy 2.0 with SQLite locally and PostgreSQL in production

* **Status:** Accepted
* **Date:** 2026-09-24

## Context

The project must run with zero infrastructure on a laptop (double-click
installer) and also deploy to Cloud Run with a managed database. Contributors
should never have to hand-edit a database to get a working state.

## Decision

* SQLAlchemy 2.0 declarative models with typed `Mapped[]` columns.
* `DATABASE_URL` selects the backend; empty means SQLite at
  `data/logistics.db`. PostgreSQL uses `psycopg` 3 (`postgres` extra).
* An idempotent seeder converges the schema and reference data on every
  startup (API lifespan, CLI, MCP server) and before every test.
* The SQLite file is **not** versioned; tests use a temporary database.

## Consequences

* Same code path for both backends; `pool_pre_ping` enabled for network DBs.
* No migration tool yet. Schema changes currently rely on `create_all` plus a
  reseed; Alembic is the obvious next step once the schema stabilises.
* Repository methods return plain dicts, keeping ORM objects out of the graph
  state (which must be JSON-serialisable for checkpoints).
