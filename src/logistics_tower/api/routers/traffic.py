"""Google Maps Routes API v2 integration (live traffic and road geometry)."""

from fastapi import APIRouter, HTTPException, Query

from logistics_tower.api.schemas import TrafficStatusResponse
from logistics_tower.services.traffic_service import get_traffic_service

router = APIRouter(prefix="/api/traffic", tags=["Traffic & Maps"])


@router.get("/status", response_model=TrafficStatusResponse)
def get_traffic_status() -> TrafficStatusResponse:
    available = get_traffic_service().is_available()
    return TrafficStatusResponse(
        provider="google_maps_routes_v2",
        configured=available,
        live_traffic_enabled=available,
        message=(
            "Google Maps Routes API v2 ativa com tráfego em tempo real."
            if available
            else "Chave GOOGLE_MAPS_API_KEY não configurada; usando estimativa haversine."
        ),
    )


@router.get("/route")
def get_traffic_route(
    origin_lat: float = Query(ge=-90, le=90),
    origin_lng: float = Query(ge=-180, le=180),
    dest_lat: float = Query(ge=-90, le=90),
    dest_lng: float = Query(ge=-180, le=180),
):
    """Road polyline, distance and traffic-aware duration between two coordinates."""
    svc = get_traffic_service()
    if not svc.is_available():
        raise HTTPException(status_code=503, detail="Google Maps API não configurada.")
    route = svc.get_route_with_traffic(origin_lat, origin_lng, dest_lat, dest_lng)
    if not route:
        raise HTTPException(status_code=502, detail="Não foi possível obter rota com tráfego do Google Maps.")
    return route
