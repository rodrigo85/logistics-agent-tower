"""Interactive dashboard (Leaflet map) and the JSON feed that backs it."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from logistics_tower.api.dependencies import get_graph, get_plan_cache, thread_config
from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository
from logistics_tower.services.traffic_service import get_traffic_service

router = APIRouter(tags=["Dashboard"])

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def get_dashboard() -> HTMLResponse:
    html_file = _TEMPLATE_DIR / "dashboard.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Logistics Control Tower Dashboard</h1><p>Template not found.</p>", status_code=500)


@router.get("/api/dashboard-data")
def get_dashboard_data():
    """Fleet, pending orders and the latest planned routes for map and table rendering."""
    repo = get_repository()
    cache = get_plan_cache()
    return {
        "cd_id": settings.default_cd_id,
        "cd_name": settings.cd_name,
        "cd_address": settings.cd_address,
        "cd_lat": settings.cd_lat,
        "cd_lng": settings.cd_lng,
        "fleet": repo.get_available_fleet(settings.default_cd_id),
        "orders": repo.get_pending_orders(settings.default_cd_id),
        "routes": cache.routes,
        "load_allocation": cache.load_allocation,
        "unallocated_orders": cache.unallocated_orders,
        "skipped_orders": repo.get_orders_by_status("SKIPPED", settings.default_cd_id),
        "plan_thread_id": cache.thread_id,
        "plan_status": cache.status,
        "google_traffic_active": get_traffic_service().is_available(),
    }


@router.get("/api/thread-state/{thread_id}")
def get_thread_state(thread_id: str):
    """Raw LangGraph state values (routes, loads, warnings) for a given thread."""
    snapshot = get_graph().get_state(thread_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found")
    return snapshot.values
