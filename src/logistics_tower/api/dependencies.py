"""
Process-wide singletons shared by the API routers.

The compiled LangGraph application, its checkpointer and the latest-plan cache are
owned by `services.dispatch_service.DispatchPlanner`; this module only exposes them
to the routers.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from logistics_tower.services.dispatch_service import (
    DispatchPlanner,
    PlanCache,
    get_dispatch_planner,
    is_paused_at_hitl,
    thread_config,
)

__all__ = [
    "DispatchPlanner",
    "PlanCache",
    "get_dispatch_planner",
    "get_graph",
    "get_plan_cache",
    "is_paused_at_hitl",
    "thread_config",
]


def get_graph() -> CompiledStateGraph:
    return get_dispatch_planner().graph


def get_plan_cache() -> PlanCache:
    return get_dispatch_planner().latest


def config_for(thread_id: str) -> RunnableConfig:
    return thread_config(thread_id)


def latest_values() -> dict[str, Any]:
    cache = get_plan_cache()
    return {"routes": cache.routes, "load_allocation": cache.load_allocation}
