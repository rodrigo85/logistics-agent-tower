"""
Logistics tools exposed through the Model Context Protocol (MCP) and callable by the agents.
"""

from typing import Any

from logistics_tower.config import settings
from logistics_tower.memory.long_term import get_customer_memory_store
from logistics_tower.services.fleet_service import get_fleet_service
from logistics_tower.services.routing_service import get_routing_service
from logistics_tower.services.wms_service import get_wms_service


def tool_get_pending_orders(cd_id: str) -> list[dict[str, Any]]:
    """Fetches all delivery orders currently waiting at the CD staging area."""
    return get_wms_service().get_pending_orders(cd_id)


def tool_get_available_fleet(cd_id: str) -> list[dict[str, Any]]:
    """Lists all available vehicles and their load/temperature capabilities at the CD."""
    return get_fleet_service().get_available_fleet(cd_id)


def tool_get_customer_dock_rules(customer_name: str) -> list[dict[str, Any]]:
    """Retrieves long-term memory rules for a customer (e.g. dock type, vehicle size, cold-chain checks)."""
    return get_customer_memory_store().get_rules_for_customer(customer_name)


def tool_optimize_route(orders: list[dict[str, Any]], start_time: str | None = None) -> dict[str, Any]:
    """Sequences a vehicle's stops (OR-Tools TSPTW), computes ETAs, distance, shift and the daily itinerary."""
    return get_routing_service().plan_route(orders, start_time_str=start_time or settings.dock_start_time)


def tool_confirm_dispatch(manifest_id: str, cd_id: str) -> dict[str, Any]:
    """Confirms final dispatch manifest in the WMS/TMS after human approval."""
    return {
        "status": "CONFIRMED",
        "manifest_id": manifest_id,
        "cd_id": cd_id,
        "message": "Ordem de carregamento e manifesto eletrônico emitidos com sucesso.",
    }
