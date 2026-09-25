"""
Model Context Protocol (MCP) Server for WMS/TMS Logistics Systems.
Exposes logistics tools and operational resources to autonomous agents using MCP 2.x standards.
"""

import json

from mcp.server.mcpserver import MCPServer

from logistics_tower.config import settings
from logistics_tower.mcp.tools import (
    tool_confirm_dispatch,
    tool_find_customers,
    tool_get_available_fleet,
    tool_get_customer_dock_rules,
    tool_get_pending_orders,
    tool_list_orders,
    tool_move_customer_orders,
    tool_optimize_route,
    tool_remember_note,
    tool_reschedule_customer_window,
    tool_restore_customer_today,
    tool_skip_customer_today,
)

# Initialize MCP 2.x Server
mcp_server = MCPServer(name="wms-tms-logistics-server")


@mcp_server.tool()
def get_pending_orders(cd_id: str = settings.default_cd_id, delivery_date: str = "hoje") -> str:
    """Fetches the delivery orders waiting at the CD for one delivery date (hoje, amanhã, quinta, 27/09, ISO)."""
    orders = tool_get_pending_orders(cd_id, delivery_date)
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


@mcp_server.tool()
def find_customers(query: str) -> str:
    """Searches customers by name, code, neighbourhood or city and returns candidates with today's order counts."""
    return json.dumps(tool_find_customers(query), ensure_ascii=False)


@mcp_server.tool()
def skip_customer_today(customer: str, reason: str = "Solicitado pelo despachante", date: str = "hoje") -> str:
    """Removes a customer's orders of one delivery date from that day's plan (kept in the WMS as SKIPPED)."""
    return json.dumps(tool_skip_customer_today(customer, reason, date), ensure_ascii=False)


@mcp_server.tool()
def restore_customer_today(customer: str, date: str = "hoje") -> str:
    """Puts a customer's skipped orders of one delivery date back into the plan."""
    return json.dumps(tool_restore_customer_today(customer, date), ensure_ascii=False)


@mcp_server.tool()
def move_customer_orders(customer: str, to_date: str, from_date: str = "hoje") -> str:
    """Moves a customer's orders from one delivery date to another (amanhã, quinta, 27/09, ISO)."""
    return json.dumps(tool_move_customer_orders(customer, to_date, from_date), ensure_ascii=False)


@mcp_server.tool()
def reschedule_customer_window(
    customer: str, window_start: str, window_end: str, remember: bool = True, date: str = "hoje"
) -> str:
    """Sets the receiving window (HH:MM) of a customer's orders on one delivery date and optionally remembers it."""
    return json.dumps(
        tool_reschedule_customer_window(customer, window_start, window_end, remember, date), ensure_ascii=False
    )


@mcp_server.tool()
def list_orders(status: str = "PENDING", date: str = "hoje") -> str:
    """Lists the orders of one delivery date ("todos" = whole horizon) by status (PENDING, SKIPPED, DISPATCHED)."""
    return json.dumps(tool_list_orders(status, date), ensure_ascii=False)


@mcp_server.tool()
def remember_note(note: str) -> str:
    """Stores a standing instruction from the dispatcher in long-term memory."""
    return json.dumps(tool_remember_note(note), ensure_ascii=False)


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
