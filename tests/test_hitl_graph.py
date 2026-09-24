"""Unit tests for LangGraph Multi-Agent Orchestration & Human-in-the-Loop Gate."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from logistics_tower.graph import build_logistics_graph


def test_graph_hitl_interrupt_and_approval():
    checkpointer = MemorySaver()
    graph = build_logistics_graph(checkpointer=checkpointer)

    thread_id = "test-thread-hitl-01"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "cd_id": "CD-ITAJAI-SC01",
        "requires_human_approval": False,
        "human_verdict": None,
        "execution_log": [],
    }

    # First invocation: Should reach hitl_gate and pause because risks were flagged!
    graph.invoke(initial_state, config=config)
    curr_state = graph.get_state(config)

    # Assert paused at interrupt
    assert any(t.interrupts for t in curr_state.tasks), "Graph should pause at Human-in-the-Loop gate"

    # Human supervisor approves the dispatch
    resumed = graph.invoke(
        Command(resume={"verdict": "APPROVED", "feedback": "Despacho autorizado com ressalvas"}),
        config=config,
    )

    # Assert graph resumed to completion and emitted manifest
    manifest = resumed.get("dispatch_manifest")
    assert manifest is not None
    assert manifest["status"] == "DISPATCHED"
    assert manifest["total_orders_dispatched"] > 0
    assert manifest["total_vehicles_assigned"] > 0


def test_graph_hitl_interrupt_and_rejection():
    checkpointer = MemorySaver()
    graph = build_logistics_graph(checkpointer=checkpointer)

    thread_id = "test-thread-hitl-reject"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "cd_id": "CD-ITAJAI-SC01",
        "requires_human_approval": False,
        "human_verdict": None,
        "execution_log": [],
    }

    # Pause at HITL gate
    graph.invoke(initial_state, config=config)

    # Human supervisor rejects the dispatch
    resumed = graph.invoke(
        Command(resume={"verdict": "REJECTED", "feedback": "Sobrecarga de frota inaceitavel"}),
        config=config,
    )

    # Manifest should be None or cancelled
    manifest = resumed.get("dispatch_manifest")
    assert manifest is None
