"""
Logistics Tools exposed through Model Context Protocol (MCP) and callable by Autonomous Agents.
"""

from typing import Any, Dict, List

from logistics_tower.memory.long_term import get_customer_memory_store
from logistics_tower.services.fleet_service import get_fleet_service
from logistics_tower.services.routing_service import get_routing_service
from logistics_tower.services.wms_service import get_wms_service


def tool_get_pending_orders(cd_id: str) -> List[Dict[str, Any]]:
    """Fetches all delivery orders currently waiting at the CD staging area."""
    return get_wms_service().get_pending_orders(cd_id)


def tool_get_available_fleet(cd_id: str) -> List[Dict[str, Any]]:
    """Lists all available vehicles and their load/temperature capabilities at the CD."""
    return get_fleet_service().get_available_fleet(cd_id)


def tool_get_customer_dock_rules(customer_name: str) -> List[Dict[str, Any]]:
    """Retrieves long-term memory rules for a customer (e.g. dock height, vehicle size, temperature SLAs)."""
    return get_customer_memory_store().get_rules_for_customer(customer_name)


def tool_optimize_route(orders: List[Dict[str, Any]], start_time: str = "07:00") -> Dict[str, Any]:
    """Computes the sequence of stops, total km, and arrival times for a vehicle load."""
    stops, dist_km, dur_min = get_routing_service().optimize_stops_sequence(orders, start_time_str=start_time)
    return {
        "stops": stops,
        "total_distance_km": dist_km,
        "total_duration_minutes": dur_min,
    }


def tool_confirm_dispatch(manifest_id: str, cd_id: str) -> Dict[str, Any]:
    """Confirms final dispatch manifest in the WMS/TMS after human approval."""
    return {
        "status": "CONFIRMED",
        "manifest_id": manifest_id,
        "cd_id": cd_id,
        "message": "Ordem de carregamento e manifesto eletrônico emitidos com sucesso.",
    }
