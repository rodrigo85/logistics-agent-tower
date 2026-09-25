"""
Supervisor / Dispatcher Orchestration Agent.
Central coordinator of the Logistics Control Tower, routing operational tasks,
incorporating long-term customer memory, and issuing final dispatch manifests in the SQL database.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from logistics_tower.config import settings
from logistics_tower.dates import today
from logistics_tower.db.repository import get_repository
from logistics_tower.mcp.client import get_mcp_client
from logistics_tower.memory.long_term import get_customer_memory_store
from logistics_tower.state import DispatchManifest, LogisticsAgentState

logger = logging.getLogger(__name__)


def supervisor_init_node(state: LogisticsAgentState) -> dict[str, Any]:
    """
    Supervisor Initialization:
    Loads long-term customer dock rules from relational database and prepares operational environment.
    """
    cd_id = state.get("cd_id", settings.default_cd_id)
    plan_date = state.get("plan_date") or today().isoformat()
    logger.info(f"Supervisor: Initializing dispatch planning for {cd_id} on {plan_date}")

    memory_store = get_customer_memory_store()
    customer_rules = memory_store.get_all_rules()

    log_msg = (
        f"Supervisor: Session initialized for {cd_id} ({plan_date}) with {len(customer_rules)} "
        "persistent customer rules from database."
    )
    return {
        "cd_id": cd_id,
        "plan_date": plan_date,
        "customer_rules": customer_rules,
        "execution_log": [log_msg],
        "requires_human_approval": False,
        "human_verdict": None,
    }


def supervisor_finalize_node(state: LogisticsAgentState) -> dict[str, Any]:
    """
    Supervisor Finalization:
    Compiles final Dispatch Manifest, confirms via MCP tool, and persists to SQL database.
    """
    cd_id = state.get("cd_id", settings.default_cd_id)
    routes = state.get("routes", [])
    loads = state.get("load_allocation", [])

    total_orders = sum(len(load.get("orders", [])) for load in loads)
    total_w = sum(load.get("total_weight_kg", 0.0) for load in loads)
    total_v = sum(load.get("total_volume_m3", 0.0) for load in loads)

    manifest_id = f"MAN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # Confirm via MCP
    mcp = get_mcp_client()
    mcp.call_tool("confirm_dispatch_manifest", manifest_id=manifest_id, cd_id=cd_id)

    manifest_status = "DISPATCHED" if state.get("human_verdict") != "REJECTED" else "REJECTED"

    manifest: DispatchManifest = {
        "manifest_id": manifest_id,
        "cd_id": cd_id,
        "plan_date": state.get("plan_date") or today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "total_orders_dispatched": total_orders,
        "total_vehicles_assigned": len(routes),
        "total_weight_kg": round(total_w, 1),
        "total_volume_m3": round(total_v, 1),
        "routes": routes,
        "status": manifest_status,
    }

    # Persist in SQL database
    repo = get_repository()
    repo.save_dispatch_manifest(
        manifest_id=manifest_id,
        cd_id=cd_id,
        plan_date=state.get("plan_date") or today().isoformat(),
        total_orders=total_orders,
        total_vehicles=len(routes),
        total_weight_kg=round(total_w, 1),
        total_volume_m3=round(total_v, 1),
        status=manifest_status,
        human_verdict=state.get("human_verdict"),
        human_feedback=state.get("human_feedback"),
        manifest_dict=manifest,
    )

    log_msg = (
        f"Supervisor: Dispatch manifest {manifest_id} generated and persisted to database. Status: {manifest_status}"
    )
    logger.info(log_msg)

    return {
        "dispatch_manifest": manifest,
        "execution_log": [*state.get("execution_log", []), log_msg],
    }
