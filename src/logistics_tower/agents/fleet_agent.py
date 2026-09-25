"""
Fleet & Capacity Allocation Specialist Agent.
Responsible for bin-packing orders into available fleet vehicles, respecting
weight limits, volumetric cubage, and temperature control (refrigerated vs dry).
"""

import logging
from typing import Any

from logistics_tower.config import settings
from logistics_tower.mcp.client import get_mcp_client
from logistics_tower.services.fleet_service import get_fleet_service
from logistics_tower.state import LogisticsAgentState

logger = logging.getLogger(__name__)


def fleet_agent_node(state: LogisticsAgentState) -> dict[str, Any]:
    """
    Fleet Agent:
    1. Fetches pending orders and available vehicles via MCP.
    2. Retrieves long-term memory constraints (dock size, VUC requirements).
    3. Allocates orders into vehicles.
    """
    cd_id = state.get("cd_id", settings.default_cd_id)
    mcp = get_mcp_client()

    plan_date = state.get("plan_date")
    orders = state.get("raw_orders") or mcp.call_tool("get_pending_orders", cd_id=cd_id, delivery_date=plan_date)
    fleet = state.get("available_fleet") or mcp.call_tool("get_available_fleet", cd_id=cd_id)
    customer_rules = state.get("customer_rules", [])

    logger.info(f"FleetAgent: Allocating {len(orders)} orders across {len(fleet)} vehicles")

    fleet_service = get_fleet_service()
    load_allocation = fleet_service.pack_orders_into_fleet(
        orders=orders,
        fleet=fleet,
        customer_rules=customer_rules,
    )
    unallocated = list(fleet_service.last_unallocated)
    allocated = sum(len(load["orders"]) for load in load_allocation)

    log_msg = (
        f"FleetAgent: {allocated}/{len(orders)} pedidos agrupados em {len(load_allocation)} rotas "
        f"(varredura geográfica, máx. {settings.max_stops_per_vehicle} paradas por veículo)."
    )
    if unallocated:
        log_msg += f" {len(unallocated)} pedido(s) sem veículo permanecem pendentes."
    logger.info(log_msg)

    return {
        "raw_orders": orders,
        "available_fleet": fleet,
        "load_allocation": load_allocation,
        "unallocated_orders": unallocated,
        "execution_log": [*state.get("execution_log", []), log_msg],
    }
