"""
Pydantic schemas for the Logistics Control Tower REST API.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class DispatchRequest(BaseModel):
    cd_id: str = Field(default="CD-SP01-CAJAMAR", description="Distribution Center identifier")
    auto_approve: bool = Field(default=False, description="Whether to bypass Human-in-the-Loop interruptions")


class ResumeHITLRequest(BaseModel):
    thread_id: str = Field(description="Active execution thread paused at HITL gate")
    verdict: Literal["APPROVED", "REJECTED", "OVERRIDE"] = Field(
        default="APPROVED", description="Human decision"
    )
    feedback: Optional[str] = Field(default="", description="Operator notes or reasoning")


class DispatchResponse(BaseModel):
    thread_id: str
    status: Literal["COMPLETED", "AWAITING_HUMAN_APPROVAL", "REJECTED"]
    requires_approval: bool
    approval_reason: Optional[str] = None
    risk_warnings: List[Dict[str, Any]] = []
    manifest: Optional[Dict[str, Any]] = None
    execution_log: List[str] = []
