"""
ASGI entry point: `uvicorn logistics_tower.api.main:app`.

The application itself is assembled in `logistics_tower.api.app.create_app`.
"""

import uvicorn

from logistics_tower.api.app import create_app
from logistics_tower.config import settings

app = create_app()


def start() -> None:
    """Console entry point (`logistics-tower-api`) for local development with auto-reload."""
    uvicorn.run(
        "logistics_tower.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.env == "development",
    )


if __name__ == "__main__":
    start()
