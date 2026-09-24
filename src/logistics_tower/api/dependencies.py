"""
Process-wide singletons shared by the API routers.

The compiled LangGraph application and its checkpointer live for the lifetime of the
process so that Human-in-the-Loop threads can be resumed across requests.
"""

from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from logistics_tower.graph import build_logistics_graph
from logistics_tower.memory.short_term import get_session_checkpointer


@lru_cache(maxsize=1)
def get_graph() -> CompiledStateGraph:
    """Compiled multi-agent graph bound to the in-memory checkpointer."""
    return build_logistics_graph(checkpointer=get_session_checkpointer())


class PlanCache:
    """Holds the most recent plan so the dashboard can render routes without a thread id."""

    def __init__(self) -> None:
        self.routes: list[dict[str, Any]] = []
        self.load_allocation: list[dict[str, Any]] = []

    def update(self, values: dict[str, Any] | None) -> None:
        if not values:
            return
        self.routes = values.get("routes", []) or []
        self.load_allocation = values.get("load_allocation", []) or []

    def clear(self) -> None:
        self.routes = []
        self.load_allocation = []


@lru_cache(maxsize=1)
def get_plan_cache() -> PlanCache:
    return PlanCache()


def is_paused_at_hitl(state: Any) -> bool:
    """True when the LangGraph state snapshot is waiting on a human interrupt."""
    return bool(state.tasks and any(t.interrupts for t in state.tasks))


def thread_config(thread_id: str) -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": thread_id})
