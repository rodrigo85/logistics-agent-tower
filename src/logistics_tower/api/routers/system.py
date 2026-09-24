"""Health and introspection endpoints."""

from fastapi import APIRouter

from logistics_tower import __version__
from logistics_tower.api.schemas import HealthResponse
from logistics_tower.config import settings
from logistics_tower.mcp.client import get_mcp_client

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, version=__version__, env=settings.env)


@router.get("/mcp/tools")
def list_mcp_tools():
    """Lists the tools exposed to the agents through the Model Context Protocol boundary."""
    return {"tools": get_mcp_client().list_tools()}
