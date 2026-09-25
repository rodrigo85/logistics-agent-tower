"""
Dispatch planner: the single place that runs the multi-agent graph.

Used by the REST API, the CLI and the copilot's `replan` tool, so every caller
shares the same compiled graph, checkpointer (HITL threads) and "latest plan"
cache that feeds the dashboard.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository
from logistics_tower.graph import build_logistics_graph
from logistics_tower.memory.short_term import get_session_checkpointer

logger = logging.getLogger(__name__)


class PlanCache:
    """Holds the most recent plan so the dashboard can render routes without a thread id."""

    def __init__(self) -> None:
        self.thread_id: str | None = None
        self.status: str | None = None
        self.routes: list[dict[str, Any]] = []
        self.load_allocation: list[dict[str, Any]] = []
        self.unallocated_orders: list[dict[str, Any]] = []
        self.risk_warnings: list[dict[str, Any]] = []

    def update(self, thread_id: str, status: str, values: dict[str, Any] | None) -> None:
        self.thread_id = thread_id
        self.status = status
        if not values:
            return
        self.routes = values.get("routes", []) or []
        self.load_allocation = values.get("load_allocation", []) or []
        self.unallocated_orders = values.get("unallocated_orders", []) or []
        self.risk_warnings = values.get("risk_warnings", []) or []

    def clear(self) -> None:
        self.thread_id = None
        self.status = None
        self.routes = []
        self.load_allocation = []
        self.unallocated_orders = []
        self.risk_warnings = []


def thread_config(thread_id: str) -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": thread_id})


def is_paused_at_hitl(snapshot: Any) -> bool:
    return bool(snapshot.tasks and any(t.interrupts for t in snapshot.tasks))


class DispatchPlanner:
    def __init__(self) -> None:
        self.graph: CompiledStateGraph = build_logistics_graph(checkpointer=get_session_checkpointer())
        self.latest = PlanCache()

    # ------------------------------------------------------------ helpers
    def _outcome(self, thread_id: str, values: dict[str, Any], paused: bool) -> dict[str, Any]:
        manifest = values.get("dispatch_manifest")
        status = "AWAITING_HUMAN_APPROVAL" if paused else ("COMPLETED" if manifest else "REJECTED")
        return {
            "thread_id": thread_id,
            "status": status,
            "requires_approval": paused,
            "approval_reason": values.get("human_approval_reason") if paused or not manifest else None,
            "risk_warnings": values.get("risk_warnings", []) or [],
            "manifest": manifest,
            "execution_log": values.get("execution_log", []) or [],
        }

    # ------------------------------------------------------------ actions
    def plan(self, cd_id: str | None = None, auto_approve: bool = False) -> dict[str, Any]:
        """Run the agents for today's pending orders; pauses at the HITL gate when risks are flagged."""
        cd = cd_id or settings.default_cd_id
        thread_id = f"dispatch-{uuid.uuid4().hex[:8]}"
        config = thread_config(thread_id)
        get_repository().reset_orders_status(cd)

        initial_state: dict[str, Any] = {
            "cd_id": cd,
            "auto_approve": auto_approve,
            "requires_human_approval": False,
            "human_verdict": None,
            "execution_log": [],
        }
        output = self.graph.invoke(initial_state, config=config)
        snapshot = self.graph.get_state(config)
        values = snapshot.values or output or {}
        paused = is_paused_at_hitl(snapshot)
        outcome = self._outcome(thread_id, values if paused else output, paused)
        self.latest.update(thread_id, outcome["status"], values)
        logger.info("Dispatch plan %s -> %s", thread_id, outcome["status"])
        return outcome

    def resume(self, thread_id: str, verdict: str, feedback: str = "") -> dict[str, Any] | None:
        """Resume a paused thread with the human verdict. Returns None when the thread is unknown."""
        config = thread_config(thread_id)
        if not self.graph.get_state(config).values:
            return None
        output = self.graph.invoke(Command(resume={"verdict": verdict, "feedback": feedback}), config=config)
        outcome = self._outcome(thread_id, output, paused=False)
        if outcome["manifest"]:
            self.latest.update(thread_id, outcome["status"], self.graph.get_state(config).values)
        return outcome

    def status(self, thread_id: str) -> dict[str, Any] | None:
        config = thread_config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            return None
        return self._outcome(thread_id, snapshot.values, is_paused_at_hitl(snapshot))

    def state_values(self, thread_id: str) -> dict[str, Any] | None:
        snapshot = self.graph.get_state(thread_config(thread_id))
        return snapshot.values or None

    def summary(self) -> dict[str, Any]:
        """Compact description of the latest plan for the copilot and the `/agents` endpoint."""
        latest = self.latest
        routes = []
        for r in latest.routes:
            stops = r.get("stops", [])
            routes.append(
                {
                    "vehicle": f"{r.get('plate')} ({r.get('vehicle_type')})",
                    "stops": len(stops),
                    "customers": [s.get("customer_name") for s in stops],
                    "total_distance_km": r.get("total_distance_km"),
                    "shift": f"{r.get('shift_start')} -> {r.get('shift_end')}",
                    "late_stops": [s.get("customer_name") for s in stops if not s.get("on_time", True)],
                    "within_shift_limit": r.get("within_shift_limit", True),
                }
            )
        return {
            "thread_id": latest.thread_id,
            "status": latest.status,
            "routes": routes,
            "unallocated_orders": [o.get("customer_name") for o in latest.unallocated_orders],
            "risk_warnings": [f"{w.get('category')}: {w.get('description')}" for w in latest.risk_warnings][:12],
        }


@lru_cache(maxsize=1)
def get_dispatch_planner() -> DispatchPlanner:
    return DispatchPlanner()
