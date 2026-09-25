"""Dispatch planning, Human-in-the-Loop resumption and thread inspection."""

from fastapi import APIRouter, HTTPException, status

from logistics_tower.api.dependencies import get_dispatch_planner
from logistics_tower.api.schemas import DispatchRequest, DispatchResponse, ResumeHITLRequest

router = APIRouter(prefix="/dispatch", tags=["Dispatch Operations"])


@router.post("/plan", response_model=DispatchResponse, status_code=status.HTTP_200_OK)
def plan_dispatch(req: DispatchRequest) -> DispatchResponse:
    """
    Runs the multi-agent planning pipeline (fleet -> routing -> risk).
    When operational risks are flagged, execution pauses at the HITL gate and the
    response carries `requires_approval=True` with the reason.
    """
    return DispatchResponse(
        **get_dispatch_planner().plan(req.cd_id, auto_approve=req.auto_approve, plan_date=req.plan_date)
    )


@router.post("/resume", response_model=DispatchResponse)
def resume_dispatch_hitl(req: ResumeHITLRequest) -> DispatchResponse:
    """Resumes a thread paused at the HITL gate with the supervisor's verdict."""
    outcome = get_dispatch_planner().resume(req.thread_id, req.verdict, req.feedback)
    if outcome is None:
        raise HTTPException(status_code=404, detail=f"Thread {req.thread_id} not found.")
    return DispatchResponse(**outcome)


@router.get("/{thread_id}", response_model=DispatchResponse)
def get_dispatch_status(thread_id: str) -> DispatchResponse:
    """Returns the current state of a dispatch thread from the checkpointer."""
    outcome = get_dispatch_planner().status(thread_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found.")
    return DispatchResponse(**outcome)
