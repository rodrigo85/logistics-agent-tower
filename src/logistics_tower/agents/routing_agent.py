"""
Route Sequencing & Optimization Specialist Agent.
Turns each vehicle load into a sequenced multi-stop route with ETAs, distance and itinerary.
"""

import logging
from typing import Any

from logistics_tower.config import settings
from logistics_tower.mcp.client import get_mcp_client
from logistics_tower.services.traffic_service import get_traffic_service
from logistics_tower.state import LogisticsAgentState, VehicleRoute

logger = logging.getLogger(__name__)


def routing_agent_node(state: LogisticsAgentState) -> dict[str, Any]:
    """Calls the `optimize_vehicle_route` tool once per vehicle load."""
    loads = state.get("load_allocation", [])
    mcp = get_mcp_client()

    routes: list[VehicleRoute] = []
    total_km_all = 0.0
    total_stops = 0

    for load in loads:
        orders = load.get("orders", [])
        if not orders:
            continue

        plan = mcp.call_tool("optimize_vehicle_route", orders=orders, start_time=settings.dock_start_time)
        total_km_all += plan["total_distance_km"]
        total_stops += len(plan["stops"])
        routes.append(
            {
                "vehicle_id": load["vehicle_id"],
                "plate": load.get("plate", ""),
                "driver_name": load.get("driver_name", "N/A"),
                "driver_phone": load.get("driver_phone") or "",
                "vehicle_model": load.get("vehicle_model", "N/A"),
                "vehicle_type": load.get("vehicle_type", "VUC"),
                "max_weight_kg": load.get("max_weight_kg", 0.0),
                "max_volume_m3": load.get("max_volume_m3", 0.0),
                "total_distance_km": plan["total_distance_km"],
                "total_estimated_duration_min": plan["total_duration_minutes"],
                "shift_start": plan["shift_start"],
                "shift_end": plan["shift_end"],
                "within_shift_limit": plan["within_shift_limit"],
                "stops": plan["stops"],
                "itinerary": plan.get("itinerary", []),
            }
        )

    traffic_suffix = " com tráfego ao vivo (Google Maps)" if get_traffic_service().is_available() else ""
    log_msg = (
        f"RoutingAgent: {len(routes)} rotas sequenciadas pelo OR-Tools, {total_stops} paradas, "
        f"{round(total_km_all, 1)} km{traffic_suffix}."
    )
    logger.info(log_msg)

    return {
        "routes": routes,
        "execution_log": [*state.get("execution_log", []), log_msg],
    }
