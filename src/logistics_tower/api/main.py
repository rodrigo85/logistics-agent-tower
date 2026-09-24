"""
FastAPI Server for Logistics Control Tower.
Exposes multi-agent dispatch planning, Human-in-the-Loop breakpoint inspection,
MCP tools exploration, and an Interactive Visual Dashboard with Leaflet map.
"""

from pathlib import Path
import uuid
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from langgraph.types import Command

from logistics_tower.api.schemas import DispatchRequest, DispatchResponse, ResumeHITLRequest
from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository
from logistics_tower.graph import build_logistics_graph
from logistics_tower.mcp.client import get_mcp_client
from logistics_tower.memory.short_term import get_session_checkpointer

app = FastAPI(
    title="Logistics Control Tower API",
    description="Autonomous Multi-Agent Dispatch & Route Optimization with LangGraph, MCP, and Human-in-the-Loop.",
    version="1.0.0",
)

# Shared in-memory checkpointer & compiled graph
_checkpointer = get_session_checkpointer()
_graph_app = build_logistics_graph(checkpointer=_checkpointer)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def get_dashboard():
    """Serves the interactive visual dispatch control tower dashboard with Leaflet map."""
    html_file = _TEMPLATE_DIR / "dashboard.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Logistics Control Tower Dashboard</h1><p>Template not found.</p>")


@app.get("/api/dashboard-data", tags=["Dashboard"])
def get_dashboard_data():
    """Returns database fleet and pending orders for dashboard rendering."""
    repo = get_repository()
    return {
        "cd_id": settings.default_cd_id,
        "cd_name": settings.cd_name,
        "cd_address": settings.cd_address,
        "fleet": repo.get_available_fleet(settings.default_cd_id),
        "orders": repo.get_pending_orders(settings.default_cd_id),
    }


@app.get("/api/thread-state/{thread_id}", tags=["Dashboard"])
def get_thread_state(thread_id: str):
    """Returns detailed state values (routes, loads) for map and table rendering."""
    config = {"configurable": {"thread_id": thread_id}}
    curr_state = _graph_app.get_state(config)
    if not curr_state.values:
        raise HTTPException(status_code=404, detail="Thread not found")
    return curr_state.values


@app.get("/health", tags=["Monitoring"])
def health_check() -> Dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.env}


@app.get("/mcp/tools", tags=["MCP Tools"])
def list_mcp_tools():
    """Lists tools registered and exposed via Model Context Protocol (MCP)."""
    return {"tools": get_mcp_client().list_tools()}


@app.post(
    "/dispatch/plan",
    response_model=DispatchResponse,
    status_code=status.HTTP_200_OK,
    tags=["Dispatch Operations"],
)
def plan_dispatch(req: DispatchRequest):
    """
    Triggers multi-agent planning. If operational risks (overweight, late windows)
    are flagged, execution pauses at the HITL gate for human supervisor review.
    """
    thread_id = f"dispatch-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # Reset orders to PENDING for the new run
    repo = get_repository()
    repo.reset_orders_status(req.cd_id)

    initial_state = {
        "cd_id": req.cd_id,
        "requires_human_approval": False,
        "human_verdict": "APPROVED" if req.auto_approve else None,
        "execution_log": [],
    }

    # Run graph until completion or HITL interrupt
    final_output = _graph_app.invoke(initial_state, config=config)
    curr_state = _graph_app.get_state(config)

    # Check if the graph is paused waiting for human approval
    is_paused = bool(curr_state.tasks and any(t.interrupts for t in curr_state.tasks))

    if is_paused:
        values = curr_state.values
        return DispatchResponse(
            thread_id=thread_id,
            status="AWAITING_HUMAN_APPROVAL",
            requires_approval=True,
            approval_reason=values.get("human_approval_reason"),
            risk_warnings=values.get("risk_warnings", []),
            manifest=None,
            execution_log=values.get("execution_log", []),
        )

    # Completed directly
    manifest = final_output.get("dispatch_manifest")
    return DispatchResponse(
        thread_id=thread_id,
        status="COMPLETED" if manifest else "REJECTED",
        requires_approval=False,
        approval_reason=None,
        risk_warnings=final_output.get("risk_warnings", []),
        manifest=manifest,
        execution_log=final_output.get("execution_log", []),
    )


@app.post(
    "/dispatch/resume",
    response_model=DispatchResponse,
    tags=["Dispatch Operations"],
)
def resume_dispatch_hitl(req: ResumeHITLRequest):
    """
    Resumes a paused dispatch thread with the human supervisor's verdict (APPROVED / REJECTED).
    """
    config = {"configurable": {"thread_id": req.thread_id}}
    curr_state = _graph_app.get_state(config)

    if not curr_state.values:
        raise HTTPException(status_code=404, detail=f"Thread {req.thread_id} not found.")

    # Resume graph execution passing human decision
    resumed_output = _graph_app.invoke(
        Command(resume={"verdict": req.verdict, "feedback": req.feedback}),
        config=config,
    )

    manifest = resumed_output.get("dispatch_manifest")
    return DispatchResponse(
        thread_id=req.thread_id,
        status="COMPLETED" if manifest else "REJECTED",
        requires_approval=False,
        approval_reason=resumed_output.get("human_approval_reason"),
        risk_warnings=resumed_output.get("risk_warnings", []),
        manifest=manifest,
        execution_log=resumed_output.get("execution_log", []),
    )


@app.get("/dispatch/{thread_id}", response_model=DispatchResponse, tags=["Dispatch Operations"])
def get_dispatch_status(thread_id: str):
    """Fetches current thread state from the checkpointer."""
    config = {"configurable": {"thread_id": thread_id}}
    curr_state = _graph_app.get_state(config)

    if not curr_state.values:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found.")

    is_paused = bool(curr_state.tasks and any(t.interrupts for t in curr_state.tasks))
    values = curr_state.values

    return DispatchResponse(
        thread_id=thread_id,
        status="AWAITING_HUMAN_APPROVAL" if is_paused else ("COMPLETED" if values.get("dispatch_manifest") else "REJECTED"),
        requires_approval=is_paused,
        approval_reason=values.get("human_approval_reason"),
        risk_warnings=values.get("risk_warnings", []),
        manifest=values.get("dispatch_manifest"),
        execution_log=values.get("execution_log", []),
    )


def start():
    uvicorn.run("logistics_tower.api.main:app", host=settings.api_host, port=settings.api_port, reload=True)


if __name__ == "__main__":
    start()
