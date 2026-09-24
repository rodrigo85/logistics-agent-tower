"""Tests for the LangGraph multi-agent orchestration and the Human-in-the-Loop gate."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from logistics_tower.config import settings
from logistics_tower.graph import build_logistics_graph


def _initial_state() -> dict:
    return {
        "cd_id": settings.default_cd_id,
        "requires_human_approval": False,
        "human_verdict": None,
        "execution_log": [],
    }


def test_graph_runs_all_agents_and_produces_multi_stop_routes():
    graph = build_logistics_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-thread-plan"}}

    graph.invoke(_initial_state(), config=config)
    values = graph.get_state(config).values

    assert values["customer_rules"], "supervisor must load long-term customer rules"
    assert values["load_allocation"], "fleet agent must build loads"
    assert values["routes"], "routing agent must build routes"
    assert sum(len(r["stops"]) for r in values["routes"]) == 40
    assert all(len(r["stops"]) <= settings.max_stops_per_vehicle for r in values["routes"])
    assert all(r["itinerary"][0]["time_start"] == "05:00" for r in values["routes"])
    assert len(values["execution_log"]) >= 4


def test_graph_hitl_interrupt_and_approval(force_hitl):
    graph = build_logistics_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-thread-hitl-01"}}

    graph.invoke(_initial_state(), config=config)
    snapshot = graph.get_state(config)
    assert any(t.interrupts for t in snapshot.tasks), "graph should pause at the Human-in-the-Loop gate"
    assert snapshot.values["requires_human_approval"] is True

    resumed = graph.invoke(
        Command(resume={"verdict": "APPROVED", "feedback": "Despacho autorizado com ressalvas"}),
        config=config,
    )

    manifest = resumed.get("dispatch_manifest")
    assert manifest is not None
    assert manifest["status"] == "DISPATCHED"
    assert manifest["total_orders_dispatched"] == 40
    assert manifest["total_vehicles_assigned"] == len(resumed["routes"])


def test_graph_hitl_interrupt_and_rejection(force_hitl):
    graph = build_logistics_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-thread-hitl-reject"}}

    graph.invoke(_initial_state(), config=config)
    resumed = graph.invoke(
        Command(resume={"verdict": "REJECTED", "feedback": "Sobrecarga de frota inaceitável"}),
        config=config,
    )
    assert resumed.get("dispatch_manifest") is None


def test_graph_auto_approve_skips_the_gate(force_hitl, monkeypatch):
    monkeypatch.setattr(settings, "hitl_auto_approve", True)
    graph = build_logistics_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-thread-auto"}}

    result = graph.invoke(_initial_state(), config=config)
    assert not any(t.interrupts for t in graph.get_state(config).tasks)
    assert result["dispatch_manifest"]["status"] == "DISPATCHED"
