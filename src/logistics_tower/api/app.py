"""
FastAPI application factory.

Responsibilities:
- configure logging once per process;
- initialise and seed the database on startup (idempotent);
- mount the routers (dashboard, dispatch, fleet, orders, traffic, system).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from logistics_tower import __version__
from logistics_tower.api.routers import dashboard, dispatch, fleet, orders, system, traffic
from logistics_tower.config import settings
from logistics_tower.db.seed import seed_database
from logistics_tower.logging_setup import configure_logging

logger = logging.getLogger(__name__)

_DESCRIPTION = """
Autonomous multi-agent dispatch and route optimisation for a distribution center.

* **LangGraph** orchestrates Supervisor, Fleet, Routing and Risk agents with a Human-in-the-Loop gate.
* **Google OR-Tools** solves the capacitated VRP with time windows.
* **Model Context Protocol** exposes WMS/TMS tools to the agents.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    seed_database()
    logger.info("Logistics Agent Tower %s ready (env=%s, cd=%s)", __version__, settings.env, settings.default_cd_id)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Logistics Agent Tower API",
        description=_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        contact={"name": "Rodrigo Andreatta da Costa"},
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )

    app.include_router(system.router)
    app.include_router(dashboard.router)
    app.include_router(dispatch.router)
    app.include_router(fleet.router)
    app.include_router(orders.router)
    app.include_router(traffic.router)
    return app
