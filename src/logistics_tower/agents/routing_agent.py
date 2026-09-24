"""
Route Sequencing & Optimization Specialist Agent.
Takes vehicle loads and calculates optimal waypoint sequences, ETAs, and road distance.
"""

import logging
from typing import Any, Dict, List

from logistics_tower.mcp.client import get_mcp_client
from logistics_tower.state import LogisticsAgentState, VehicleRoute

logger = logging.getLogger(__name__)


def routing_agent_node(state: LogisticsAgentState) -> Dict[str, Any]:
    """
    Routing Agent:
    Computes sequence of customer deliveries for each vehicle load via MCP / Routing Service.
    """
    loads = state.get("load_allocation", [])
    mcp = get_mcp_client()

    routes: List[VehicleRoute] = []
    total_km_all = 0.0

    for load in loads:
        vehicle_id = load["vehicle_id"]
        orders = load["orders"]

        if not orders:
            continue

        route_data = mcp.call_tool("optimize_vehicle_route", orders=orders, start_time="07:00")
        stops = route_data["stops"]
        dist_km = route_data["total_distance_km"]
        dur_min = route_data["total_duration_minutes"]

        total_km_all += dist_km
        routes.append(
            {
                "vehicle_id": vehicle_id,
                "driver_name": load.get("driver_name", "N/A"),
                "vehicle_model": load.get("vehicle_model", "N/A"),
                "total_distance_km": dist_km,
                "total_estimated_duration_min": dur_min,
                "stops": stops,
            }
        )

    log_msg = f"RoutingAgent: Optimized {len(routes)} routes totaling {round(total_km_all, 1)} km."
    logger.info(log_msg)

    return {
        "routes": routes,
        "execution_log": state.get("execution_log", []) + [log_msg],
    }
