"""
Model Context Protocol (MCP) Server for WMS/TMS Logistics Systems.
Exposes logistics tools and operational resources to autonomous agents using MCP 2.x standards.
"""

import json

from mcp.server.mcpserver import MCPServer

from logistics_tower.config import settings
from logistics_tower.mcp.tools import (
    tool_confirm_dispatch,
    tool_get_available_fleet,
    tool_get_customer_dock_rules,
    tool_get_pending_orders,
    tool_optimize_route,
)

# Initialize MCP 2.x Server
mcp_server = MCPServer(name="wms-tms-logistics-server")


@mcp_server.tool()
def get_pending_orders(cd_id: str = settings.default_cd_id) -> str:
    """Fetches all delivery orders currently waiting at the CD staging area for dispatch."""
    orders = tool_get_pending_orders(cd_id)
    return json.dumps(orders, ensure_ascii=False)


@mcp_server.tool()
def get_available_fleet(cd_id: str = settings.default_cd_id) -> str:
    """Lists all available delivery vehicles at the CD with their capacity and refrigeration status."""
    fleet = tool_get_available_fleet(cd_id)
    return json.dumps(fleet, ensure_ascii=False)


@mcp_server.tool()
def get_customer_dock_rules(customer_name: str) -> str:
    """Retrieves long-term memory restrictions for a customer (e.g. dock constraints, vehicle limits)."""
    rules = tool_get_customer_dock_rules(customer_name)
    return json.dumps(rules, ensure_ascii=False)


@mcp_server.tool()
def optimize_vehicle_route(orders_json: str, start_time: str = settings.dock_start_time) -> str:
    """Computes the optimized sequence of stops, total distance (km), and arrival ETA for a vehicle."""
    try:
        orders = json.loads(orders_json)
    except Exception:
        orders = []
    res = tool_optimize_route(orders, start_time=start_time)
    return json.dumps(res, ensure_ascii=False)


@mcp_server.tool()
def confirm_dispatch_manifest(manifest_id: str, cd_id: str = settings.default_cd_id) -> str:
    """Emits the final electronic dispatch manifest in the WMS/TMS after supervisor human sign-off."""
    res = tool_confirm_dispatch(manifest_id, cd_id)
    return json.dumps(res, ensure_ascii=False)


@mcp_server.resource("wms://orders/summary")
def get_orders_summary() -> str:
    """Resource returning real-time summary of pending orders in the CD."""
    orders = tool_get_pending_orders(settings.default_cd_id)
    total_kg = sum(o.get("weight_kg", 0) for o in orders)
    total_m3 = sum(o.get("volume_m3", 0) for o in orders)
    return json.dumps(
        {
            "cd_id": settings.default_cd_id,
            "order_count": len(orders),
            "total_weight_kg": round(total_kg, 1),
            "total_volume_m3": round(total_m3, 1),
        },
        ensure_ascii=False,
    )


@mcp_server.resource("tms://fleet/summary")
def get_fleet_summary() -> str:
    """Resource returning active fleet availability status."""
    fleet = tool_get_available_fleet(settings.default_cd_id)
    return json.dumps(
        {
            "cd_id": settings.default_cd_id,
            "available_vehicles": len(fleet),
            "vehicles": [f"{v['vehicle_id']} ({v['vehicle_type']})" for v in fleet],
        },
        ensure_ascii=False,
    )


def run_mcp_server():
    """Runs the MCP server using standard I/O transport."""
    from logistics_tower.db.seed import seed_database
    from logistics_tower.logging_setup import configure_logging

    configure_logging()
    seed_database()
    mcp_server.run()


if __name__ == "__main__":
    run_mcp_server()
