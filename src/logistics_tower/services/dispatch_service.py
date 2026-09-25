"""
Dispatch planner: the single place that runs the multi-agent graph.

Used by the REST API, the CLI and the copilot's `replan` tool, so every caller
shares the same compiled graph, checkpointer (HITL threads) and the per-day
"latest plan" caches that feed the dashboard.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from logistics_tower.config import settings
from logistics_tower.dates import label_for, parse_delivery_date, planning_days
from logistics_tower.db.repository import get_repository
from logistics_tower.graph import build_logistics_graph
from logistics_tower.memory.short_term import get_session_checkpointer

logger = logging.getLogger(__name__)


class PlanCache:
    """Holds the most recent plan of one delivery day so the dashboard can render it without a thread id."""

    def __init__(self, plan_date: date) -> None:
        self.plan_date = plan_date
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


def _to_date(value: str | date | None) -> date:
    return value if isinstance(value, date) else parse_delivery_date(value)


class DispatchPlanner:
    def __init__(self) -> None:
        self.graph: CompiledStateGraph = build_logistics_graph(checkpointer=get_session_checkpointer())
        self._plans: dict[str, PlanCache] = {}
        self._latest_date: date | None = None

    # ------------------------------------------------------------ caches
    def for_date(self, plan_date: str | date | None = None) -> PlanCache:
        day = _to_date(plan_date)
        key = day.isoformat()
        if key not in self._plans:
            self._plans[key] = PlanCache(day)
        return self._plans[key]

    @property
    def latest(self) -> PlanCache:
        """Plan of the most recently planned day (today when nothing was planned yet)."""
        return self.for_date(self._latest_date)

    def clear_all(self) -> None:
        self._plans.clear()
        self._latest_date = None

    # ------------------------------------------------------------ helpers
    def _outcome(self, thread_id: str, plan_date: date, values: dict[str, Any], paused: bool) -> dict[str, Any]:
        manifest = values.get("dispatch_manifest")
        status = "AWAITING_HUMAN_APPROVAL" if paused else ("COMPLETED" if manifest else "REJECTED")
        return {
            "thread_id": thread_id,
            "plan_date": plan_date.isoformat(),
            "status": status,
            "requires_approval": paused,
            "approval_reason": values.get("human_approval_reason") if paused or not manifest else None,
            "risk_warnings": values.get("risk_warnings", []) or [],
            "manifest": manifest,
            "execution_log": values.get("execution_log", []) or [],
        }

    # ------------------------------------------------------------ actions
    def plan(
        self, cd_id: str | None = None, auto_approve: bool = False, plan_date: str | date | None = None
    ) -> dict[str, Any]:
        """Run the agents for one day's pending orders; pauses at the HITL gate when risks are flagged."""
        cd = cd_id or settings.default_cd_id
        day = _to_date(plan_date)
        thread_id = f"dispatch-{day.strftime('%m%d')}-{uuid.uuid4().hex[:6]}"
        config = thread_config(thread_id)
        get_repository().reset_orders_status(cd, delivery_date=day)

        initial_state: dict[str, Any] = {
            "cd_id": cd,
            "plan_date": day.isoformat(),
            "auto_approve": auto_approve,
            "requires_human_approval": False,
            "human_verdict": None,
            "execution_log": [],
        }
        output = self.graph.invoke(initial_state, config=config)
        snapshot = self.graph.get_state(config)
        values = snapshot.values or output or {}
        paused = is_paused_at_hitl(snapshot)
        outcome = self._outcome(thread_id, day, values if paused else output, paused)
        self.for_date(day).update(thread_id, outcome["status"], values)
        self._latest_date = day
        logger.info("Dispatch plan %s (%s) -> %s", thread_id, day.isoformat(), outcome["status"])
        return outcome

    def resume(self, thread_id: str, verdict: str, feedback: str = "") -> dict[str, Any] | None:
        """Resume a paused thread with the human verdict. Returns None when the thread is unknown."""
        config = thread_config(thread_id)
        before = self.graph.get_state(config).values
        if not before:
            return None
        day = parse_delivery_date(before.get("plan_date"))
        output = self.graph.invoke(Command(resume={"verdict": verdict, "feedback": feedback}), config=config)
        outcome = self._outcome(thread_id, day, output, paused=False)
        if outcome["manifest"]:
            self.for_date(day).update(thread_id, outcome["status"], self.graph.get_state(config).values)
        return outcome

    def status(self, thread_id: str) -> dict[str, Any] | None:
        config = thread_config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            return None
        day = parse_delivery_date(snapshot.values.get("plan_date"))
        return self._outcome(thread_id, day, snapshot.values, is_paused_at_hitl(snapshot))

    def state_values(self, thread_id: str) -> dict[str, Any] | None:
        snapshot = self.graph.get_state(thread_config(thread_id))
        return snapshot.values or None

    # ------------------------------------------------------------ summaries
    def summary(self, plan_date: str | date | None = None) -> dict[str, Any]:
        """Compact description of one day's latest plan for the copilot and the `/agents` endpoint."""
        cache = self.for_date(plan_date) if plan_date is not None else self.latest
        routes = []
        for r in cache.routes:
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
            "plan_date": cache.plan_date.isoformat(),
            "plan_date_label": label_for(cache.plan_date),
            "thread_id": cache.thread_id,
            "status": cache.status,
            "routes": routes,
            "unallocated_orders": [o.get("customer_name") for o in cache.unallocated_orders],
            "risk_warnings": [f"{w.get('category')}: {w.get('description')}" for w in cache.risk_warnings][:12],
        }

    def horizon(self) -> list[dict[str, Any]]:
        """Planning days with order counts and plan status (dashboard tabs, copilot prompt)."""
        counts = {row["date"]: row for row in get_repository().get_day_summary(settings.default_cd_id)}
        rows = []
        for day in planning_days():
            key = day.isoformat()
            cache = self._plans.get(key)
            rows.append(
                {
                    "date": key,
                    "label": label_for(day),
                    "weekday": day.strftime("%A"),
                    "pending": counts.get(key, {}).get("pending", 0),
                    "dispatched": counts.get(key, {}).get("dispatched", 0),
                    "skipped": counts.get(key, {}).get("skipped", 0),
                    "plan_status": cache.status if cache else None,
                    "plan_thread_id": cache.thread_id if cache else None,
                    "routes": len(cache.routes) if cache else 0,
                }
            )
        return rows


@lru_cache(maxsize=1)
def get_dispatch_planner() -> DispatchPlanner:
    return DispatchPlanner()
