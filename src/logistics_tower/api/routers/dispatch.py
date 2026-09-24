"""Dispatch planning, Human-in-the-Loop resumption and thread inspection."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from langgraph.types import Command

from logistics_tower.api.dependencies import get_graph, get_plan_cache, is_paused_at_hitl, thread_config
from logistics_tower.api.schemas import DispatchRequest, DispatchResponse, DispatchStatus, ResumeHITLRequest
from logistics_tower.db.repository import get_repository

router = APIRouter(prefix="/dispatch", tags=["Dispatch Operations"])


@router.post("/plan", response_model=DispatchResponse, status_code=status.HTTP_200_OK)
def plan_dispatch(req: DispatchRequest) -> DispatchResponse:
    """
    Runs the multi-agent planning pipeline (fleet -> routing -> risk).
    When operational risks are flagged, execution pauses at the HITL gate and the
    response carries `requires_approval=True` with the reason.
    """
    graph = get_graph()
    thread_id = f"dispatch-{uuid.uuid4().hex[:8]}"
    config = thread_config(thread_id)

    get_repository().reset_orders_status(req.cd_id)

    initial_state: dict[str, Any] = {
        "cd_id": req.cd_id,
        "requires_human_approval": False,
        "human_verdict": "APPROVED" if req.auto_approve else None,
        "execution_log": [],
    }

    final_output = graph.invoke(initial_state, config=config)
    snapshot = graph.get_state(config)
    values = snapshot.values or final_output or {}

    get_plan_cache().update(values)

    if is_paused_at_hitl(snapshot):
        return DispatchResponse(
            thread_id=thread_id,
            status="AWAITING_HUMAN_APPROVAL",
            requires_approval=True,
            approval_reason=values.get("human_approval_reason"),
            risk_warnings=values.get("risk_warnings", []),
            manifest=None,
            execution_log=values.get("execution_log", []),
        )

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


@router.post("/resume", response_model=DispatchResponse)
def resume_dispatch_hitl(req: ResumeHITLRequest) -> DispatchResponse:
    """Resumes a thread paused at the HITL gate with the supervisor's verdict."""
    graph = get_graph()
    config = thread_config(req.thread_id)

    if not graph.get_state(config).values:
        raise HTTPException(status_code=404, detail=f"Thread {req.thread_id} not found.")

    resumed = graph.invoke(Command(resume={"verdict": req.verdict, "feedback": req.feedback}), config=config)

    manifest = resumed.get("dispatch_manifest")
    if manifest and "routes" in manifest:
        get_plan_cache().routes = manifest.get("routes", [])

    return DispatchResponse(
        thread_id=req.thread_id,
        status="COMPLETED" if manifest else "REJECTED",
        requires_approval=False,
        approval_reason=resumed.get("human_approval_reason"),
        risk_warnings=resumed.get("risk_warnings", []),
        manifest=manifest,
        execution_log=resumed.get("execution_log", []),
    )


@router.get("/{thread_id}", response_model=DispatchResponse)
def get_dispatch_status(thread_id: str) -> DispatchResponse:
    """Returns the current state of a dispatch thread from the checkpointer."""
    graph = get_graph()
    snapshot = graph.get_state(thread_config(thread_id))

    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found.")

    paused = is_paused_at_hitl(snapshot)
    values = snapshot.values
    current_status: DispatchStatus
    if paused:
        current_status = "AWAITING_HUMAN_APPROVAL"
    else:
        current_status = "COMPLETED" if values.get("dispatch_manifest") else "REJECTED"

    return DispatchResponse(
        thread_id=thread_id,
        status=current_status,
        requires_approval=paused,
        approval_reason=values.get("human_approval_reason"),
        risk_warnings=values.get("risk_warnings", []),
        manifest=values.get("dispatch_manifest"),
        execution_log=values.get("execution_log", []),
    )
