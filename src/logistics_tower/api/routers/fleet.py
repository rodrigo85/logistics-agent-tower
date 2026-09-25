"""Fleet and per-vehicle itinerary endpoints."""

from fastapi import APIRouter, HTTPException

from logistics_tower.api.dependencies import get_dispatch_planner
from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository

router = APIRouter(prefix="/api/vehicle", tags=["Fleet"])


def _normalise(identifier: str) -> str:
    return identifier.replace("-", "").strip().upper()


@router.get("/{identifier}/itinerary")
def get_vehicle_itinerary(identifier: str):
    """
    Daily itinerary (loading, transit, unloading, return, lunch) for a vehicle,
    looked up by licence plate or vehicle id. Falls back to the base profile when
    no plan has been generated yet.
    """
    wanted = _normalise(identifier)

    for route in get_dispatch_planner().latest.routes:
        if wanted in (_normalise(route.get("plate", "")), _normalise(route.get("vehicle_id", ""))):
            return route

    for v in get_repository().get_available_fleet(settings.default_cd_id):
        if wanted in (_normalise(v.get("plate", "")), _normalise(v.get("vehicle_id", ""))):
            return {
                "vehicle_id": v["vehicle_id"],
                "plate": v["plate"],
                "driver_name": v["driver_name"],
                "driver_phone": v.get("driver_phone"),
                "vehicle_model": v["model"],
                "vehicle_type": v["vehicle_type"],
                "max_weight_kg": v["max_weight_kg"],
                "max_volume_m3": v["max_volume_m3"],
                "total_distance_km": 0.0,
                "total_estimated_duration_min": 0.0,
                "stops": [],
                "itinerary": [],
                "status": "AVAILABLE",
            }

    raise HTTPException(status_code=404, detail=f"Vehicle '{identifier}' not found (plate or vehicle id).")
