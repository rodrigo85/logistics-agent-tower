"""
LangGraph Multi-Agent DAG for Logistics Control Tower.
Wires together Supervisor, Fleet, Routing, and Risk specialist agents,
with a Human-in-the-Loop (HITL) interrupt gate before final dispatch.
"""

import logging
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from logistics_tower.agents.fleet_agent import fleet_agent_node
from logistics_tower.agents.risk_agent import risk_agent_node
from logistics_tower.agents.routing_agent import routing_agent_node
from logistics_tower.agents.supervisor import supervisor_finalize_node, supervisor_init_node
from logistics_tower.config import settings
from logistics_tower.memory.short_term import get_session_checkpointer
from logistics_tower.state import LogisticsAgentState

logger = logging.getLogger(__name__)


def hitl_gate_node(state: LogisticsAgentState) -> Dict[str, Any]:
    """
    Human-in-the-Loop (HITL) Gate:
    If capacity or SLA risk is flagged, pauses graph execution using LangGraph interrupt().
    The graph state is persisted in checkpointer until human input resumes it.
    """
    requires_approval = state.get("requires_human_approval", False)
    auto_approve = settings.hitl_auto_approve

    if requires_approval and not auto_approve:
        logger.warning("HITL: Pausing graph for human dispatcher review.")
        payload = {
            "status": "AWAITING_HUMAN_APPROVAL",
            "reason": state.get("human_approval_reason"),
            "risk_warnings": state.get("risk_warnings", []),
            "prompt": "Foram detectadas exceções operacionais. Aprove, rejeite ou comente o despacho.",
        }
        human_response = interrupt(payload)

        # Once resumed, process human decision
        if isinstance(human_response, dict):
            verdict = human_response.get("verdict", "APPROVED").upper()
            feedback = human_response.get("feedback", "")
        else:
            verdict = str(human_response).upper()
            feedback = ""

        return {
            "human_verdict": verdict,
            "human_feedback": feedback,
            "execution_log": state.get("execution_log", []) + [f"HITL: Despachante respondeu: {verdict}. Feedback: {feedback}"],
        }

    return {
        "human_verdict": "APPROVED",
        "human_feedback": "Aprovação automática ou nenhuma inconsistência crítica.",
        "execution_log": state.get("execution_log", []) + ["HITL: Plano aprovado sem interrupções."],
    }


def reject_dispatch_node(state: LogisticsAgentState) -> Dict[str, Any]:
    """Handles dispatch cancellation when rejected by human operator."""
    log_msg = f"Supervisor: Despacho cancelado pelo operador humano. Motivo: {state.get('human_feedback', 'N/A')}"
    logger.warning(log_msg)
    return {
        "dispatch_manifest": None,
        "execution_log": state.get("execution_log", []) + [log_msg],
    }


def decide_after_hitl(state: LogisticsAgentState) -> str:
    """Routes to finalize or rejection based on human decision."""
    verdict = state.get("human_verdict", "APPROVED")
    if verdict == "REJECTED":
        return "reject_dispatch"
    return "supervisor_finalize"


def build_logistics_graph(checkpointer: Any = None):
    """
    Compiles the multi-agent StateGraph with checkpointer for HITL interruption/resumption.
    """
    workflow = StateGraph(LogisticsAgentState)

    # Register nodes
    workflow.add_node("supervisor_init", supervisor_init_node)
    workflow.add_node("fleet_agent", fleet_agent_node)
    workflow.add_node("routing_agent", routing_agent_node)
    workflow.add_node("risk_agent", risk_agent_node)
    workflow.add_node("hitl_gate", hitl_gate_node)
    workflow.add_node("supervisor_finalize", supervisor_finalize_node)
    workflow.add_node("reject_dispatch", reject_dispatch_node)

    # Connect DAG flow
    workflow.add_edge(START, "supervisor_init")
    workflow.add_edge("supervisor_init", "fleet_agent")
    workflow.add_edge("fleet_agent", "routing_agent")
    workflow.add_edge("routing_agent", "risk_agent")
    workflow.add_edge("risk_agent", "hitl_gate")

    # Conditional edge after HITL
    workflow.add_conditional_edges(
        "hitl_gate",
        decide_after_hitl,
        {
            "supervisor_finalize": "supervisor_finalize",
            "reject_dispatch": "reject_dispatch",
        },
    )

    workflow.add_edge("supervisor_finalize", END)
    workflow.add_edge("reject_dispatch", END)

    cp = checkpointer if checkpointer is not None else get_session_checkpointer()
    return workflow.compile(checkpointer=cp)


if __name__ == "__main__":
    app = build_logistics_graph()
    print("[OK] Logistics Control Tower Multi-Agent DAG compiled successfully!")
