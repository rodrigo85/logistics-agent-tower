"""Dispatcher Copilot (conversational agent) and agent-registry endpoints."""

import logging
import uuid

from fastapi import APIRouter, HTTPException

from logistics_tower import __version__
from logistics_tower.agents.copilot import build_tools, get_copilot
from logistics_tower.api.dependencies import get_dispatch_planner
from logistics_tower.api.schemas import AgentsResponse, ChatRequest, ChatResponse, CopilotStatusResponse
from logistics_tower.config import settings
from logistics_tower.llm.provider import LLMNotConfiguredError, llm_status
from logistics_tower.mcp.client import get_mcp_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Copilot"])


@router.get("/copilot/status", response_model=CopilotStatusResponse)
def copilot_status() -> CopilotStatusResponse:
    return CopilotStatusResponse(**llm_status(), tools=[t.name for t in build_tools()])


@router.post("/copilot/chat", response_model=ChatResponse)
def copilot_chat(req: ChatRequest) -> ChatResponse:
    """
    Sends an operator instruction to the copilot. Mutating instructions (skip a customer,
    reschedule a receiving window) are applied to today's orders and the plan is recomputed.
    """
    thread_id = req.thread_id or f"chat-{uuid.uuid4().hex[:8]}"
    try:
        result = get_copilot().chat(req.message, thread_id)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=f"LLM indisponível: {exc}") from exc
    except Exception as exc:
        logger.exception("Copilot failure")
        raise HTTPException(status_code=502, detail=f"Falha ao consultar o LLM: {exc}") from exc
    return ChatResponse(**result)


@router.get("/agents", response_model=AgentsResponse)
def list_agents() -> AgentsResponse:
    """Registry of the agents in this process, their tools and the LLM/plan status (lifecycle view)."""
    planner = get_dispatch_planner()
    status = llm_status()
    return AgentsResponse(
        version=__version__,
        env=settings.env,
        planning_agents=[
            {"name": "supervisor", "kind": "deterministic", "role": "init + long-term memory, final manifest"},
            {"name": "fleet_agent", "kind": "deterministic", "role": "sweep clustering into one route per truck"},
            {"name": "routing_agent", "kind": "deterministic", "role": "OR-Tools TSPTW sequencing and itinerary"},
            {"name": "risk_agent", "kind": "deterministic", "role": "capacity, SLA, shift and unallocated audit"},
            {"name": "hitl_gate", "kind": "human", "role": "interrupt / resume with dispatcher verdict"},
            {
                "name": "copilot",
                "kind": "llm",
                "role": "conversational operator agent",
                "provider": status["provider"],
                "model": status["model"],
                "available": status["available"],
            },
        ],
        mcp_tools=[t["name"] for t in get_mcp_client().list_tools()],
        copilot_tools=[t.name for t in build_tools()],
        latest_plan={"thread_id": planner.latest.thread_id, "status": planner.latest.status},
    )
